/* Place-only visit drafts never enter browser history or map reports. */
(function (root) {
  "use strict";
  function create({
    node,
    api,
    notify,
    onSaved,
    checkpoint = () => () => true,
    newId = () => crypto.randomUUID().replaceAll("-", ""),
  }) {
    const drafts = new Map();
    function render(target, place, current, today) {
      let draft = drafts.get(place.id);
      if (!draft) {
        draft = {
          id: newId(),
          note: "",
          day: today,
          files: [],
          uploaded: 0,
          busy: false,
          saved: false,
          complete: false,
        };
        drafts.set(place.id, draft);
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
      const another = node("button", "Add another visit");
      another.type = "button";
      another.onclick = () => {
        if (draft.busy) return;
        drafts.delete(place.id);
        target.replaceChildren();
        render(target, place, current, today);
      };
      saved.append(
        node("p", "Experience saved to this place."),
        folder,
        another,
      );
      const controls = [note, day, photos];
      const update = () => {
        for (const control of controls)
          control.disabled = draft.busy || draft.saved;
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
      };
      note.oninput = () => {
        draft.note = note.value;
      };
      day.oninput = () => {
        draft.day = day.value;
      };
      photos.onchange = () => {
        draft.files = Array.from(photos.files);
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
          draft.files.length > 5 ||
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
          await api(
            `/places/${encodeURIComponent(place.id)}/experiences/${draft.id}`,
            {
              method: "PUT",
              body: { note: draft.note, visit_date: draft.day },
            },
          );
          draft.saved = true;
          onSaved(place.id);
          while (draft.uploaded < draft.files.length) {
            const body = new FormData();
            body.append("photo", draft.files[draft.uploaded]);
            await api(`/experiences/${draft.id}/photos`, {
              method: "POST",
              body,
            });
            draft.uploaded++;
          }
          draft.complete = true;
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
