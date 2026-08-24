/*
 * The Trackr link grabber
 * =======================
 * Collects the outbound application links from a Trackr listing tab so you can
 * feed them to `ajp listings add-batch`. It runs in YOUR browser, in YOUR
 * logged-in session, and only reads links already rendered on the page — it does
 * not call any private API. Still a grey area re: the site's terms; use for your
 * own personal job search.
 *
 * HOW TO USE (console):
 *   1. Open the Trackr tab you want (e.g. tech summer / tech spring).
 *   2. Scroll to the bottom so every row has loaded (these lists lazy-render).
 *   3. Open DevTools (F12) -> Console, paste this whole file, press Enter.
 *   4. The links are copied to your clipboard and printed. Paste into a file
 *      (e.g. links.txt) and run:  uv run ajp listings add-batch --file links.txt
 *      or paste directly:         uv run ajp listings add-batch <url1> <url2> ...
 *
 * If it grabs too few links, set ALL_EXTERNAL = true below (grabs every external
 * link, including some noise — the ingester safely skips non-job URLs).
 */
(() => {
  const ALL_EXTERNAL = false; // set true to grab every off-site link

  // Hosts that indicate an application / ATS page.
  const ATS = [
    "greenhouse.io", "lever.co", "myworkdayjobs.com", "workday",
    "ashbyhq.com", "teamtailor.com", "smartrecruiters.com", "workable.com",
    "recruitee.com", "jobvite.com", "icims.com", "taleo.net", "successfactors",
    "eightfold.ai", "gr8people", "oraclecloud.com", "bamboohr.com", "breezy.hr",
    "join.com", "personio", "pinpointhq", "ripplematch", "tal.net", "avature",
    "workforcenow", "wd1", "wd3", "wd5",
  ];
  const KEYWORDS = ["job", "career", "apply", "vacan", "role", "position"];

  const here = location.hostname;
  const looksLikeJob = (u) => {
    const host = u.hostname.toLowerCase();
    const full = (host + u.pathname).toLowerCase();
    if (ATS.some((a) => host.includes(a))) return true;
    return KEYWORDS.some((k) => full.includes(k));
  };

  const links = [...document.querySelectorAll("a[href]")]
    .map((a) => a.href)
    .filter((h) => /^https?:\/\//.test(h))
    .map((h) => { try { return new URL(h); } catch { return null; } })
    .filter((u) => u && u.hostname !== here)
    .filter((u) => (ALL_EXTERNAL ? true : looksLikeJob(u)))
    .map((u) => u.href);

  const unique = [...new Set(links)];
  const text = unique.join("\n");

  const done = (how) =>
    console.log(`Grabbed ${unique.length} links (${how}).\n\n${text}`);

  if (navigator.clipboard && window.isSecureContext) {
    navigator.clipboard.writeText(text).then(
      () => done("copied to clipboard"),
      () => (typeof copy === "function" ? (copy(text), done("copied via copy()")) : done("copy manually from below")),
    );
  } else if (typeof copy === "function") {
    copy(text);
    done("copied via copy()");
  } else {
    done("copy manually from below");
  }
})();
