/* Place-only visit drafts never enter browser history or map reports. */
(function (root) {
  "use strict";
  function create({
    node,
    api,
    notify,
    onSaved,
    onGenerate = async () => ({}),
    checkpoint = () => () => true,
    newId = () => crypto.randomUUID().replaceAll("-", ""),
  }) {
    const drafts = new Map();
    function render(
      target,
      place,
      current,
      today,
      existing = null,
      onComplete = async () => {},
    ) {
      const key = existing?.id || place.id;
      let draft = drafts.get(key);
      if (
        existing &&
        draft?.complete &&
        !draft.busy &&
        draft.revision !== existing.revision
      ) {
        drafts.delete(key);
        draft = null;
      }
      if (!draft) {
        draft = {
          id: existing?.id || newId(),
          revision: existing?.revision,
          note: existing?.note || "",
          day: existing
            ? new Date(existing.visit_date).toLocaleDateString("en-CA", {
                timeZone: existing.timezone || "UTC",
              })
            : today,
          existingPhotos: existing?.photos?.length || 0,
          generation: null,
          generationError: "",
          files: [],
          uploaded: 0,
          busy: false,
          saved: false,
          complete: false,
        };
        drafts.set(key, draft);
      }
      const form = node("form", undefined, "place-experience-form");
      const intro = node("p", `What was your experience at ${place.name}?`);
      const note = node("textarea");
      note.value = draft.note;
      note.required = true;
      note.minLength = 3;
      note.maxLength = 8000;
      note.rows = 3;
      note.placeholder = "What did you notice, enjoy or find difficult?";
      const noteLabel = node("label", "Your experience");
      noteLabel.append(note);
      const day = node("input");
      day.type = "date";
      day.value = draft.day;
      day.max = today;
      day.required = true;
      const dayLabel = node("label", "Visited on");
      dayLabel.append(day);
      const photos = node("input");
      photos.type = "file";
      photos.multiple = true;
      photos.accept = "image/jpeg,image/png,image/webp";
      const photoLabel = node("label", "Photos (optional)");
      photoLabel.append(photos);
      const photoHint = node("p", undefined, "hint");
      const error = node("p", undefined, "inline-error");
      error.hidden = true;
      error.setAttribute("role", "alert");
      const save = node("button", "Save experience");
      save.type = "submit";
      const saved = node("div", undefined, "place-visit-saved");
      saved.hidden = !draft.complete;
      saved.setAttribute("role", "status");
      const folder = node("a", "Open place folder");
      folder.href = "/?view=folder&place=" + encodeURIComponent(place.id);
      const another = node(
        "button",
        existing ? "Edit experience again" : "Add another visit",
      );
      another.type = "button";
      another.onclick = () => {
        if (draft.busy) return;
        if (existing) {
          draft.complete = false;
          draft.saved = false;
          draft.existingPhotos += draft.uploaded;
          draft.files = [];
          draft.uploaded = 0;
          draft.generation = null;
          draft.generationError = "";
        } else drafts.delete(key);
        target.replaceChildren();
        render(target, place, current, today, existing, onComplete);
      };
      const savedStatus = node("p", "Experience saved to this place.");
      const retry = node("button", "Retry local AI");
      retry.type = "button";
      retry.hidden = true;
      saved.append(savedStatus, folder, retry, another);
      async function generate(live, force = false) {
        draft.generationError = "";
        savedStatus.textContent =
          "Experience saved. Local AI is preparing its card and story…";
        try {
          draft.generation = await onGenerate(
            { id: draft.id, revision: draft.revision },
            live,
            force,
          );
          if (draft.generation?.card_error)
            draft.generationError = `Your experience is saved${draft.generation.journal_mode === "local AI journal" ? " and the AI journal is ready" : ""}. Card preparation failed (${draft.generation.card_error}); retry when ready.`;
          const fallback =
            draft.generation?.journal_mode === "extractive fallback";
          if (fallback && !draft.generationError)
            draft.generationError =
              "The AI could not produce a validated story. Your original experience is saved; you can retry.";
          savedStatus.textContent =
            draft.generationError ||
            (draft.generation?.card_id
              ? "Location Card and AI story are ready in the place folder."
              : "Your AI journal is ready. Add a photo to create a Location Card.");
        } catch (failure) {
          draft.generationError = `Experience and photos saved. AI preparation failed: ${failure.message}`;
          savedStatus.textContent = draft.generationError;
        }
        retry.hidden = !draft.generationError;
      }
      retry.onclick = async () => {
        if (draft.busy) return;
        draft.busy = true;
        update();
        const checkpointCurrent = checkpoint();
        try {
          await generate(() => current() && checkpointCurrent(), true);
        } finally {
          draft.busy = false;
          update();
        }
      };
      const controls = [note, day];
      const update = () => {
        for (const control of controls)
          control.disabled = draft.busy || draft.saved;
        photos.disabled = draft.busy || draft.complete;
        save.disabled = draft.busy;
        save.hidden = draft.complete;
        save.textContent = draft.busy
          ? "Saving…"
          : draft.saved
            ? "Retry remaining photos"
            : "Save experience";
        photoHint.textContent = draft.files.length
          ? `${draft.files.length} selected · ${draft.uploaded} saved. Up to 5 photos, 20 MiB each.`
          : "Up to 5 photos · 20 MiB and 40 megapixels each · JPEG, PNG or WebP.";
        saved.hidden = !draft.complete;
        retry.disabled = draft.busy;
        retry.hidden = !draft.generationError;
        if (draft.generationError)
          savedStatus.textContent = draft.generationError;
        else if (draft.generation?.card_id)
          savedStatus.textContent =
            "Location Card and AI story are ready in the place folder.";
      };
      note.oninput = () => {
        draft.note = note.value;
      };
      day.oninput = () => {
        draft.day = day.value;
      };
      photos.onchange = () => {
        draft.files = [
          ...draft.files.slice(0, draft.uploaded),
          ...photos.files,
        ];
        error.hidden = true;
        update();
      };
      form.onsubmit = async (event) => {
        event.preventDefault();
        if (draft.busy || draft.complete) return;
        const navigationCurrent = checkpoint();
        const live = () => current() && navigationCurrent();
        error.hidden = true;
        if (draft.note.trim().length < 3) {
          error.textContent = "Write a short experience first.";
          error.hidden = false;
          note.focus();
          return;
        }
        if (
          draft.files.length + draft.existingPhotos > 5 ||
          draft.files.some((file) => file.size > 20 * 1024 * 1024)
        ) {
          error.textContent =
            "Choose up to five photos, no larger than 20 MiB each.";
          error.hidden = false;
          return;
        }
        draft.busy = true;
        update();
        try {
          const stored = await api(
            `/places/${encodeURIComponent(place.id)}/experiences/${draft.id}`,
            {
              method: "PUT",
              body: {
                note: draft.note,
                visit_date: draft.day,
                source_revision: draft.revision,
              },
            },
          );
          draft.revision = stored?.revision || draft.revision;
          draft.saved = true;
          onSaved(place.id);
          while (draft.uploaded < draft.files.length) {
            const body = new FormData();
            body.append("photo", draft.files[draft.uploaded]);
            const photo = await api(`/experiences/${draft.id}/photos`, {
              method: "POST",
              body,
            });
            draft.revision = photo?.experience_revision || draft.revision;
            draft.uploaded++;
          }
          draft.complete = true;
          update();
          await generate(live);
          if (live()) await onComplete();
          if (live()) notify("Experience saved for " + place.name + ".");
        } catch (failure) {
          if (live()) {
            error.textContent = draft.saved
              ? "Experience saved. " +
                failure.message +
                " Retry the remaining photos."
              : failure.message;
            error.hidden = false;
          }
        } finally {
          draft.busy = false;
          update();
        }
      };
      form.append(
        intro,
        noteLabel,
        dayLabel,
        photoLabel,
        photoHint,
        error,
        save,
        saved,
      );
      target.append(form);
      update();
      return form;
    }
    return { render };
  }
  root.NukkadPlaceExperience = { create };
  if (typeof module !== "undefined")
    module.exports = root.NukkadPlaceExperience;
})(typeof window === "undefined" ? globalThis : window);
