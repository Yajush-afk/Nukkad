/* Place memories: the card is rendered by the server, and private drafts stay in the tab. */
(function (root) {
  "use strict";
  function create({ api, node, $, navigation, runJob, report, message }) {
    const drafts = new Map(),
      journalDrafts = new Map();
    const date = (value, timezone) =>
      new Date(value).toLocaleDateString("en", {
        day: "numeric",
        month: "short",
        year: "numeric",
        ...(timezone ? { timeZone: timezone } : {}),
      });
    const image = (photo, alt, variant = "thumbnail") => {
      const img = node("img");
      img.src = `/api/photos/${photo}/${variant}`;
      img.alt = alt;
      img.loading = "lazy";
      return img;
    };
    const download = (card) => {
      const link = node("a", "Download card PNG", "download-link");
      link.href = `/api/location-cards/${card.id}/export.png`;
      link.download = `nukkad-location-${card.id}.png`;
      return link;
    };
    const action = (text, handler, className) => {
      const button = node("button", text, className);
      button.type = "button";
      button.onclick = handler;
      return button;
    };
    const details = (title, ...children) => {
      const element = node("details", undefined, "quiet-details");
      element.append(node("summary", title), ...children);
      return element;
    };
    async function reload(place, current) {
      const folder = await api(`/collection/${encodeURIComponent(place)}`);
      if (current()) await renderFolder(folder, current);
    }
    async function load(current) {
      const collection = await api("/collection");
      if (!current()) return;
      const target = $("place-collection");
      target.replaceChildren();
      const heading = node("div", undefined, "collection-heading");
      const title = node("h2", "Places you’ve kept.");
      title.id = "place-collection-title";
      heading.append(
        title,
        node(
          "p",
          `${collection.card_count} ${collection.card_count === 1 ? "Location Card" : "Location Cards"} · ${collection.folders.length} reported ${collection.folders.length === 1 ? "place" : "places"}`,
          "collection-count",
        ),
      );
      target.append(heading);
      if (!collection.folders.length) {
        target.append(
          node(
            "p",
            "Save a reached stop after a walk, add photos, and keep its place memory here.",
            "hint",
          ),
        );
        return;
      }
      const grid = node("div", undefined, "folder-grid");
      for (const folder of collection.folders) {
        const tile = node("a", undefined, "place-folder-tile");
        tile.href = `/?view=folder&place=${encodeURIComponent(folder.id)}`;
        tile.setAttribute(
          "aria-label",
          `Open ${folder.name}, ${folder.photos} photos across ${folder.visits} visits`,
        );
        tile.onclick = (event) => {
          if (
            event.button !== 0 ||
            event.metaKey ||
            event.ctrlKey ||
            event.shiftKey ||
            event.altKey
          )
            return;
          event.preventDefault();
          void navigation.go("place-folder", folder.id);
        };
        const cover = node("div", undefined, "folder-cover");
        if (folder.cover_photo_id)
          cover.append(
            image(folder.cover_photo_id, `A saved photo from ${folder.name}`),
          );
        else
          cover.append(
            node("span", "A small memory starts here.", "folder-empty"),
          );
        const tab = node("div", undefined, "folder-tab");
        tab.append(
          node("h3", folder.name),
          node(
            "p",
            `${folder.visits} ${folder.visits === 1 ? "visit" : "visits"} · ${folder.photos} photos`,
            "hint",
          ),
        );
        const bottom = node("div", undefined, "folder-bottom");
        bottom.append(
          node(
            "span",
            folder.current_card_id
              ? folder.stale
                ? "Card needs an update"
                : "Location Card kept"
              : "No card yet",
          ),
          node("span", "↗", "folder-arrow"),
        );
        tile.append(cover, tab, bottom);
        grid.append(tile);
      }
      target.append(grid);
    }
    async function renderFolder(folder, current) {
      if (!current()) return;
      $("folder-title").textContent = folder.name;
      $("folder-caption").textContent =
        `${folder.visits.length} reported ${folder.visits.length === 1 ? "visit" : "visits"}. Your memories stay on this laptop.`;
      const target = $("folder-content");
      target.replaceChildren();
      const card = folder.current_card;
      const cardArea = node("section", undefined, "location-card-area");
      cardArea.append(node("h2", "Location CARD", "eyebrow"));
      if (card) {
        const preview = node("img", undefined, "location-card-preview");
        preview.src = `/api/location-cards/${card.id}/export.png`;
        preview.alt = `Location Card for ${folder.name}, reported ${date(card.visit_date, card.timezone)}`;
        cardArea.append(
          preview,
          node(
            "p",
            `${card.mode}${card.stale ? " · Source changed: regenerate when ready." : ""}`,
            "hint",
          ),
          download(card),
        );
        const editor = node("form", undefined, "card-editor");
        const saved = drafts.get(card.id) || card;
        const label = node(
          "label",
          "Card summary (third person, up to 40 words)",
        );
        const summary = node("textarea");
        summary.value = saved.summary;
        summary.maxLength = 320;
        summary.rows = 3;
        label.append(summary);
        const photoLabel = node("label", "Cover photo from this visit");
        const selector = node("select");
        const visit = folder.visits.find(
          (item) => item.id === card.experience_id,
        );
        for (const [index, photo] of visit.photos.entries()) {
          const option = node("option", `Photo ${index + 1}`);
          option.value = photo.id;
          selector.append(option);
        }
        selector.value = saved.photo_id;
        if (!selector.value && visit.photos.length)
          selector.value = visit.photos[0].id;
        photoLabel.append(selector);
        const sliders = [];
        for (const [key, title] of [
          ["crop_x", "Crop left / right"],
          ["crop_y", "Crop up / down"],
        ]) {
          const label = node("label", title);
          const slider = node("input");
          slider.type = "range";
          slider.min = "0";
          slider.max = "1";
          slider.step = ".01";
          slider.value = saved[key] ?? 0.5;
          label.append(slider);
          editor.append(label);
          sliders.push(slider);
        }
        const retain = () =>
          drafts.set(card.id, {
            summary: summary.value,
            photo_id: selector.value,
            crop_x: Number(sliders[0].value),
            crop_y: Number(sliders[1].value),
          });
        summary.oninput = retain;
        selector.onchange = retain;
        for (const slider of sliders) slider.oninput = retain;
        const save = node("button", "Save card edits");
        editor.prepend(label, photoLabel);
        editor.append(save);
        editor.onsubmit = async (event) => {
          event.preventDefault();
          const checkpoint = navigation.checkpoint();
          try {
            retain();
            await api(`/collection/${encodeURIComponent(folder.id)}/card`, {
              method: "PATCH",
              body: { version_id: card.id, ...drafts.get(card.id) },
            });
            drafts.delete(card.id);
            if (checkpoint()) await reload(folder.id, checkpoint);
          } catch (error) {
            if (checkpoint()) report(error);
          }
        };
        cardArea.append(details("Edit this Location Card", editor));
      } else
        cardArea.append(
          node(
            "p",
            "Choose a reported visit below to create this place’s first card.",
            "hint",
          ),
        );
      target.append(cardArea);
      const generation = node("section", undefined, "card-generation");
      generation.append(
        node("h2", card ? "Make a new version." : "Keep this visit."),
        node(
          "p",
          "One card describes one visit. Earlier versions stay saved.",
          "hint",
        ),
      );
      const visitLabel = node("label", "Reported visit");
      const visits = node("select");
      for (const visit of folder.visits) {
        const option = node(
          "option",
          `${date(visit.visit_date, visit.timezone)} · ${visit.photos.length} photos`,
        );
        option.value = visit.id;
        visits.append(option);
      }
      visitLabel.append(visits);
      generation.append(visitLabel);
      const readiness = await api("/readiness");
      if (!current()) return;
      const capable =
        readiness.local_ai_ready &&
        readiness.model_capabilities.includes("vision");
      if (!capable)
        generation.append(
          node(
            "p",
            "Local vision is unavailable for the selected model. You can create a manual template and choose its cover yourself.",
            "hint",
          ),
        );
      const buttons = node("div", undefined, "buttonrow");
      for (const [mode, title] of [
        ["ai", card ? "Regenerate with local AI" : "Create with local AI"],
        ["manual", "Create manual template"],
      ]) {
        const button = action(
          title,
          async () => {
            const checkpoint = navigation.checkpoint();
            try {
              const job = await api(
                `/collection/${encodeURIComponent(folder.id)}/generate`,
                { method: "POST", body: { experience_id: visits.value, mode } },
              );
              await runJob(
                job,
                async () => {
                  if (checkpoint()) await reload(folder.id, checkpoint);
                },
                checkpoint,
              );
            } catch (error) {
              if (checkpoint()) report(error);
            }
          },
          mode === "ai" ? "primary" : "",
        );
        button.disabled = mode === "ai" && !capable;
        buttons.append(button);
      }
      generation.append(buttons);
      target.append(generation);
      const photosArea = node("section", undefined, "visits-gallery");
      photosArea.append(node("h2", "Photos, visit by visit."));
      const journals = node("section", undefined, "place-journals");
      journals.append(node("h2", "The longer story."));
      for (const visit of folder.visits) {
        const group = node("section", undefined, "visit-group");
        group.append(
          node("h3", date(visit.visit_date, visit.timezone)),
          node("p", `${visit.photos.length} photos · Reported visit`, "hint"),
        );
        const grid = node("div", undefined, "photo-grid");
        for (const [index, photo] of visit.photos.entries()) {
          const link = node("a");
          link.href = `/api/photos/${photo.id}/display`;
          link.target = "_blank";
          link.rel = "noopener noreferrer";
          link.append(
            image(
              photo.id,
              `Photo ${index + 1} from ${folder.name}, ${date(visit.visit_date, visit.timezone)}`,
            ),
          );
          grid.append(link);
        }
        group.append(grid);
        const edit = action("Edit visit note or photos", () =>
          navigation.go("outcome", visit.outcome_id),
        );
        group.append(edit);
        photosArea.append(group);
        if (visit.note) {
          const source = node("pre", visit.note, "journal-text");
          journals.append(
            details(
              `Original experience · ${date(visit.visit_date, visit.timezone)}`,
              source,
            ),
          );
        }
        if (visit.journal) {
          const section = node("section", undefined, "journal-entry");
          section.append(
            node("h3", date(visit.visit_date, visit.timezone)),
            node(
              "p",
              `${visit.journal.mode} · ${visit.journal.status}`,
              "hint",
            ),
            node("pre", visit.journal.text, "journal-text"),
          );
          const draft = node("textarea");
          draft.value =
            journalDrafts.get(visit.journal.version_id) ?? visit.journal.text;
          draft.maxLength = 2000;
          draft.oninput = () =>
            journalDrafts.set(visit.journal.version_id, draft.value);
          draft.setAttribute(
            "aria-label",
            `Edit journal from ${date(visit.visit_date, visit.timezone)}`,
          );
          const controls = node("div", undefined, "buttonrow");
          for (const [status, text] of [
            ["accepted", "Save journal"],
            ["rejected", "Reject draft"],
          ]) {
            controls.append(
              action(text, async () => {
                const checkpoint = navigation.checkpoint();
                try {
                  await api(`/outcomes/${visit.id}/journal`, {
                    method: "PATCH",
                    body: {
                      status,
                      text: draft.value,
                      version_id: visit.journal.version_id,
                    },
                  });
                  journalDrafts.delete(visit.journal.version_id);
                  if (checkpoint()) await reload(folder.id, checkpoint);
                } catch (error) {
                  if (checkpoint()) report(error);
                }
              }),
            );
          }
          section.append(details("Review this journal", draft, controls));
          const earlier = (visit.journal_versions || []).filter(
            (item) => item.version_id !== visit.journal.version_id,
          );
          if (earlier.length) {
            const versions = node("div");
            for (const version of earlier) {
              versions.append(
                node("p", `${version.mode} · ${version.status}`, "hint"),
                node("pre", version.text, "journal-text"),
              );
            }
            section.append(
              details(
                `${earlier.length} earlier journal ${earlier.length === 1 ? "version" : "versions"}`,
                versions,
              ),
            );
          }
          journals.append(section);
        }
      }
      target.append(photosArea, journals);
      const older = folder.card_versions.filter((item) => item.id !== card?.id);
      if (older.length) {
        const versions = node("div", undefined, "card-version-list");
        for (const version of older) {
          const item = node("div");
          item.append(
            node(
              "p",
              `${date(version.created_at, version.timezone)} · ${version.mode}`,
              "hint",
            ),
            download(version),
          );
          versions.append(item);
        }
        target.append(
          details(
            `${older.length} earlier card ${older.length === 1 ? "version" : "versions"}`,
            versions,
          ),
        );
      }
    }
    return { load, renderFolder };
  }
  root.NukkadCollection = { create };
  if (typeof module !== "undefined") module.exports = root.NukkadCollection;
})(globalThis);
