import type { SourceItem } from "@/lib/types";

/** Minutes/hours/days ago as an ISO string, so fixtures never look stale. */
export function ago(hours: number): string {
  return new Date(Date.now() - hours * 3_600_000).toISOString();
}

/** A Source Item that has not been persisted yet — no id, no created_at. */
export type LiveSourceItem = Omit<SourceItem, "id" | "created_at">;

/**
 * Rival posts, already rows.
 *
 * Rivals are the one kind written on arrival: they come from a Metricool sync,
 * so there is nothing live to browse. `synced_for_page_id` is whose competitor
 * set they belong to — always 1 here, because there is one Page.
 *
 * `reactions` is the default sort on the Rivals tab, and metrics are populated
 * for rival posts only; tweets and articles leave the three columns null.
 */
export const RIVAL_POSTS: SourceItem[] = [
  {
    id: 101,
    kind: "rival_post",
    external_id: "1225577819_10160418822",
    author: "Historic Vids",
    synced_for_page_id: 1,
    text: "In 1889 a Kansas farmer traded his last mule for a broken windmill. Twelve years later the family was selling electricity to three counties. The mule, by every account, outlived the man who traded it.",
    url: "https://facebook.com/historicvids/posts/10160418822",
    image_url: null,
    published_at: ago(19),
    reactions: 41_200,
    comments: 1_884,
    shares: 6_310,
    created_at: ago(3),
  },
  {
    id: 102,
    kind: "rival_post",
    external_id: "9930277461_10159002731",
    author: "The Vintage News",
    synced_for_page_id: 1,
    text: "She was told the lighthouse would kill her within a year. Ida Lewis kept it for fifty-four, and pulled eighteen people out of Newport Harbor while she was at it.",
    url: "https://facebook.com/thevintagenews/posts/10159002731",
    image_url: null,
    published_at: ago(31),
    reactions: 28_940,
    comments: 902,
    shares: 3_115,
    created_at: ago(3),
  },
  {
    id: 103,
    kind: "rival_post",
    external_id: "4471028833_10158771204",
    author: "History Cool Kids",
    synced_for_page_id: 1,
    text: "The photograph took eight hours to expose. Everyone who walked down that Paris boulevard vanished from it — except one man who stopped to have his boots shined. He is the first human being ever photographed, and nobody knows his name.",
    url: "https://facebook.com/historycoolkids/posts/10158771204",
    image_url: null,
    published_at: ago(46),
    reactions: 96_400,
    comments: 4_120,
    shares: 21_880,
    created_at: ago(3),
  },
  {
    id: 104,
    kind: "rival_post",
    external_id: "7783340019_10157220088",
    author: "Rare Historical Photos",
    synced_for_page_id: 1,
    text: "Before refrigeration, Boston sold winter to Calcutta. Frederic Tudor cut lakes into blocks, packed them in sawdust, and shipped ice across the equator. Two thirds melted. He got rich on the third that did not.",
    url: "https://facebook.com/rarehistoricalphotos/posts/10157220088",
    image_url: null,
    published_at: ago(58),
    reactions: 12_770,
    comments: 388,
    shares: 1_402,
    created_at: ago(3),
  },
  {
    id: 105,
    kind: "rival_post",
    external_id: "2298104477_10160990312",
    author: "Historic Vids",
    synced_for_page_id: 1,
    text: "He signed the register as a plumber so the hospital would let him in. He was the surgeon. It was 1846, and the operation he was about to perform was the first under ether in Europe.",
    url: "https://facebook.com/historicvids/posts/10160990312",
    image_url: null,
    published_at: ago(72),
    reactions: 7_930,
    comments: 214,
    shares: 640,
    created_at: ago(3),
  },
  {
    id: 106,
    kind: "rival_post",
    external_id: "5510923388_10161004557",
    author: "Weird History",
    synced_for_page_id: 1,
    text: "For eleven days in 1908 the fastest thing on earth was a Thomas Flyer stuck in a Nebraska snowdrift, being pulled by borrowed horses, in a race from New York to Paris going the wrong way round the world.",
    url: "https://facebook.com/weirdhistory/posts/10161004557",
    image_url: null,
    published_at: ago(84),
    reactions: 3_505,
    comments: 96,
    shares: 271,
    created_at: ago(3),
  },
];

/**
 * One previously-ticked article, kept as a row.
 *
 * Proves the tick is what creates the row: everything else in ARTICLE_FEED is
 * live and has no id until the operator selects it.
 */
export const SAVED_SOURCES: SourceItem[] = [
  {
    id: 107,
    kind: "article",
    external_id: "https://www.smithsonianmag.com/history/the-clockmaker-who-outlived-his-clock-180987221/",
    author: "Smithsonian Magazine",
    synced_for_page_id: null,
    text: "The clockmaker who outlived his clock — and spent his last forty years being asked to fix it.",
    url: "https://www.smithsonianmag.com/history/the-clockmaker-who-outlived-his-clock-180987221/",
    image_url: null,
    published_at: ago(26),
    reactions: null,
    comments: null,
    shares: null,
    created_at: ago(2),
  },
];

/**
 * Live articles from the seven curated feeds.
 *
 * Not rows. Browsing does not write — these become Source Items only when
 * ticked into the Cart, which is what keeps the table from filling with
 * hundreds of unread articles.
 */
export const ARTICLE_FEED: LiveSourceItem[] = [
  {
    kind: "article",
    external_id: "https://www.smithsonianmag.com/history/the-woman-who-mapped-the-ocean-floor-180987410/",
    author: "Smithsonian Magazine",
    synced_for_page_id: null,
    text: "Marie Tharp drew the mid-Atlantic ridge by hand from soundings she was not allowed to collect herself, and was told her own discovery was girl talk.",
    url: "https://www.smithsonianmag.com/history/the-woman-who-mapped-the-ocean-floor-180987410/",
    image_url: null,
    published_at: ago(11),
    reactions: null,
    comments: null,
    shares: null,
  },
  {
    kind: "article",
    external_id: "https://www.atlasobscura.com/articles/the-village-that-moved-itself-uphill",
    author: "Atlas Obscura",
    synced_for_page_id: null,
    text: "When the mine beneath Kiruna began to swallow the town, Sweden decided to move the buildings rather than the ore — church, clock tower and all, three kilometres east.",
    url: "https://www.atlasobscura.com/articles/the-village-that-moved-itself-uphill",
    image_url: null,
    published_at: ago(20),
    reactions: null,
    comments: null,
    shares: null,
  },
  {
    kind: "article",
    external_id: "https://www.thehistoryblog.com/archives/71204",
    author: "The History Blog",
    synced_for_page_id: null,
    text: "A Roman shoe hoard pulled from a Northumberland ditch includes a size 13 that has no matching foot anywhere in the fort's records.",
    url: "https://www.thehistoryblog.com/archives/71204",
    image_url: null,
    published_at: ago(29),
    reactions: null,
    comments: null,
    shares: null,
  },
  {
    kind: "article",
    external_id: "https://www.historyextra.com/period/tudor/the-queens-food-taster/",
    author: "HistoryExtra",
    synced_for_page_id: null,
    text: "The job of royal food taster was hereditary, salaried, and — according to the household accounts — surprisingly survivable.",
    url: "https://www.historyextra.com/period/tudor/the-queens-food-taster/",
    image_url: null,
    published_at: ago(38),
    reactions: null,
    comments: null,
    shares: null,
  },
  {
    kind: "article",
    external_id: "https://www.livescience.com/archaeology/bronze-age-bakery-uncovered",
    author: "Live Science",
    synced_for_page_id: null,
    text: "A Bronze Age bakery found under a Cypriot car park still held the grain, the grindstones, and a fingerprint pressed into a loaf that never went in the oven.",
    url: "https://www.livescience.com/archaeology/bronze-age-bakery-uncovered",
    image_url: null,
    published_at: ago(44),
    reactions: null,
    comments: null,
    shares: null,
  },
  {
    kind: "article",
    external_id: "https://allthatsinteresting.com/the-lighthouse-keepers-of-eilean-mor",
    author: "All That's Interesting",
    synced_for_page_id: null,
    text: "Three keepers left Eilean Mor in December 1900. The lamp was trimmed, the table was set, and one oilskin coat was still on its hook.",
    url: "https://allthatsinteresting.com/the-lighthouse-keepers-of-eilean-mor",
    image_url: null,
    published_at: ago(53),
    reactions: null,
    comments: null,
    shares: null,
  },
  {
    kind: "article",
    external_id: "https://www.sciencedaily.com/releases/2026/07/260729114502.htm",
    author: "Science Daily",
    synced_for_page_id: null,
    text: "Isotope work on a medieval Icelandic graveyard suggests half the population buried there had never eaten fish, in a village with no other food.",
    url: "https://www.sciencedaily.com/releases/2026/07/260729114502.htm",
    image_url: null,
    published_at: ago(61),
    reactions: null,
    comments: null,
    shares: null,
  },
  {
    kind: "article",
    external_id: "https://www.smithsonianmag.com/smart-news/the-bell-that-rang-for-nobody-180987388/",
    author: "Smithsonian Magazine",
    synced_for_page_id: null,
    text: "For sixty-one years a bell in a Vermont mill town rang at 4:45 a.m. for a shift that had stopped existing in 1934.",
    url: "https://www.smithsonianmag.com/smart-news/the-bell-that-rang-for-nobody-180987388/",
    image_url: null,
    published_at: ago(70),
    reactions: null,
    comments: null,
    shares: null,
  },
];

/**
 * Feeds that did not answer this fetch.
 *
 * A feed that rots goes unnoticed unless its failure is on screen, so the
 * Articles tab surfaces these rather than silently returning fewer items.
 */
export const FEED_FAILURES = [
  { feed_url: "https://feeds.feedburner.com/historyextra/all", error: "504 after 10s" },
];

/**
 * Tweets resolvable by URL, keyed by the id in the pasted link.
 *
 * A tweet is one live lookup against api.x.com/2 — never a browsable list —
 * so the Tweets tab is a paste box, not a grid.
 */
export const TWEET_LOOKUP: Record<string, LiveSourceItem> = {
  "1817449230118928441": {
    kind: "tweet",
    external_id: "1817449230118928441",
    author: "@HistoryInPics",
    synced_for_page_id: null,
    text: "In 1889 the Eiffel Tower was supposed to be dismantled after twenty years. It survived because the army found it made an excellent radio antenna — and the man who saved it did so by intercepting German transmissions from the top.",
    url: "https://x.com/HistoryInPics/status/1817449230118928441",
    image_url: null,
    published_at: ago(8),
    reactions: null,
    comments: null,
    shares: null,
  },
  "1816003348871142219": {
    kind: "tweet",
    external_id: "1816003348871142219",
    author: "@qikipedia",
    synced_for_page_id: null,
    text: "The last man to be executed in the Tower of London was shot in 1941, in a miniature rifle range, sitting in an ordinary wooden chair borrowed from the officers' mess.",
    url: "https://x.com/qikipedia/status/1816003348871142219",
    image_url: null,
    published_at: ago(15),
    reactions: null,
    comments: null,
    shares: null,
  },
};
