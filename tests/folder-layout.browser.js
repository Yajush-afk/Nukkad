/* Evaluate in the collaborative preview on an isolated folder with a current card. */
(() => {
  const rect = (selector) => {
    const element = document.querySelector(selector);
    if (!element) throw Error(`Missing folder element: ${selector}`);
    return element.getBoundingClientRect();
  };
  const near = (a, b, message) => {
    if (Math.abs(a - b) > 2)
      throw Error(`${message}: ${Math.abs(a - b).toFixed(1)}px`);
  };
  const heading = rect(".folder-heading");
  const text = document.createRange();
  text.selectNodeContents(document.querySelector("#folder-title"));
  const title = text.getBoundingClientRect();
  near(
    title.left + title.width / 2,
    heading.left + heading.width / 2,
    "Folder title off centre",
  );
  if (
    rect(".folder-heading .back-button").bottom >
    rect(".folder-heading .eyebrow").top
  )
    throw Error("Back button crowds the heading text");
  const image = rect(".location-card-preview");
  const label = rect(".location-card-area h2");
  near(label.left, image.left, "Card label detached from preview");
  near(label.right, image.right, "Card label has a different width");
  near(
    rect(".location-card-area > .hint").left,
    image.left,
    "Card mode detached from preview",
  );
  near(
    rect(".location-card-area > .download-link").left,
    image.left,
    "Download detached from preview",
  );
  near(
    rect(".card-generation").left,
    image.left,
    "Card actions detached from preview",
  );
  if (
    parseFloat(
      getComputedStyle(document.querySelector(".location-card-area h2"))
        .fontSize,
    ) < 11
  )
    throw Error("Card label is too small");
  if (document.documentElement.scrollWidth > innerWidth)
    throw Error("Folder creates horizontal overflow");
  return {
    pass: true,
    viewport: innerWidth,
    cardWidth: image.width,
    titleOffset: Math.abs(
      title.left + title.width / 2 - heading.left - heading.width / 2,
    ),
  };
})();
