import type { Draft } from "@/lib/types";
import { ago } from "./sources";

/**
 * Seed Drafts, one per status the Review screen has to render.
 *
 * The copy obeys the brand rules on purpose — hook under 65 words with no
 * question, five recap lines each opening with an emoji, a first comment
 * carrying birth and death years, highlight phrases that are exact substrings
 * of the overlay text. A layout that only ever sees placeholder text has not
 * been tested; a 1,900-character first comment is what the operator actually
 * scrolls.
 *
 * Draft 487 is the exception and breaks two rules deliberately, so the warnings
 * panel is exercised rather than theoretical.
 */

const LUSTIG_BODY = `Victor Lustig (1890–1947) was born in Bohemia and spoke five languages, all of them well enough to be someone else in each. By 1925 he was working the Atlantic liners as "Count" Lustig, and he was in Paris when a newspaper item gave him the idea that made him famous.

The piece was small and bureaucratic: the Eiffel Tower was expensive to maintain, the paint bill was enormous, and the city was quietly wondering what to do about it. Lustig had stationery forged for the Ministry of Posts and Telegraphs, rented a suite at the Hôtel de Crillon, and invited six scrap-metal dealers to a confidential meeting.

The tower, he explained, had always been temporary. It was built for the 1889 exposition and was meant to come down in 1909. The government could not announce a demolition without an outcry, so the contract would be awarded privately, and discretion was a condition of bidding.

André Poisson wanted it badly enough to believe it. He was newer to Paris than the others and hungry for the contract that would make his name. When he hesitated, Lustig took him aside and confided that a civil servant's salary was thin and that a bribe would settle the matter — which is the detail that convinced him, because it was exactly how he expected the transaction to work.

Poisson paid for the Eiffel Tower and for the privilege of buying it. Lustig took the money to Vienna and waited for the arrest that never came: Poisson was too humiliated to go to the police. So Lustig came back to Paris a month later and ran it again, on a fresh set of dealers.

The second attempt failed. Someone went to the police early, and Lustig left for America, where he sold Al Capone (1899–1947) an investment that did not exist and then returned the money, buying himself a reputation for honesty that he spent for years afterwards. He died in Alcatraz. The occupation on his death certificate reads "apprentice salesman."`;

const WU_BODY = `Wu Zetian (624–705) entered the imperial palace at thirteen as a junior concubine to Emperor Taizong (598–649), a rank that came with a title, a room, and no expectation of ever being remembered.

When Taizong died she was sent to a Buddhist convent, which was where the story was supposed to end. It did not. His son, Emperor Gaozong (628–683), had noticed her while his father was still alive, and he brought her back to court. Within five years she had displaced the empress and taken the title herself, and the accusations that followed her — that she strangled her own infant daughter to frame her rival — come from histories written by men who had every reason to loathe her.

Gaozong suffered a stroke in 660. Wu took over the correspondence, then the appointments, then the decisions. For twenty-three years she governed through a husband who could not, and after his death through two sons whom she installed and removed as it suited her. She ran an examination system that promoted men on merit rather than birth, which made her enemies among precisely the families whose sons had expected the posts.

In 690 she stopped governing through anyone. She declared the Zhou dynasty, took the throne in her own name, and became the only woman in three thousand years of Chinese history to rule as emperor rather than as regent or consort. She was sixty-six.

Her fifteen years were not gentle. She kept a secret police, encouraged informers, and executed opponents in numbers that the chronicles record with relish. She also expanded the empire west, cut taxes on farmers, and left the Tang state stronger than she found it.

She was deposed at eighty-one by her own court and died months later. Her tomb outside Xi'an carries a memorial tablet seven metres high, and the tablet is blank. Nobody has ever satisfactorily explained why.`;

const LAMARR_BODY = `Hedy Lamarr (1914–2000) was, in 1942, the most photographed face at MGM and the co-holder of United States Patent 2,292,387, and only one of those facts was allowed to be public.

She was born Hedwig Kiesler in Vienna. Her first marriage, at nineteen, was to Friedrich Mandl (1900–1977), an arms manufacturer who sold munitions to Mussolini and who took his young wife to business dinners as decoration. She sat through years of technical conversation about torpedoes, guidance systems, and the problem that made them unreliable: a radio-controlled torpedo could be jammed by anyone who found its frequency.

She escaped the marriage, the story goes, by drugging a maid and leaving in her uniform. She reached London, met Louis B. Mayer (1884–1957) on the crossing, and arrived in Hollywood with a contract and a new name.

The idea came to her between films, and she worked it out with the composer George Antheil (1900–1959), whose experience was in synchronising sixteen player pianos for a concert piece. If the transmitter and the receiver hopped between frequencies together, on a sequence known only to them, there was nothing steady for an enemy to jam. Antheil's mechanism used a slotted paper roll, exactly like a pianola, running the same pattern at both ends.

They patented it and gave it to the United States Navy, which filed it, ignored it, and suggested that Lamarr would be more useful selling war bonds. She sold twenty-five million dollars' worth.

The patent expired before it earned either of them anything. Frequency hopping surfaced in Navy ships during the Cuban blockade in 1962, three years after Antheil died, and the principle now sits underneath Bluetooth, GPS and Wi-Fi. Lamarr was recognised in 1997, three years before her death, at eighty-two.`;

const RADIUM_BODY = `Grace Fryer (1899–1933) took a job at the United States Radium Corporation in Orange, New Jersey in 1917, painting luminous numerals onto watch dials for the army. The pay was three times what a factory girl could earn elsewhere, and the work was considered clean.

The brushes had to hold a fine point. The technique the company taught was called lip-pointing: roll the bristles between your lips, dip, paint, repeat. A dial painter did this several hundred times a day. The women were told the paint was harmless. Some of them painted their fingernails with it, and their teeth, to surprise their boyfriends in the dark.

Radium behaves in the body like calcium, which means the bones take it and keep it. The first symptoms looked dental. Teeth loosened and came out, and the sockets refused to heal. Dr Theodore Blum noticed in 1924 that the jawbones of these patients were dying in a pattern he had never seen, and he named it radium jaw.

The company's response was to commission its own studies, suppress the ones that agreed with Blum, and tell the women they were suffering from syphilis — a diagnosis calculated to stop anyone from pressing further in public.

Fryer spent two years finding a lawyer who would take the case. By the time five of them sued in 1927, she could not walk unaided and her jaw was held together with a brace. The trial was adjourned repeatedly on the grounds that the plaintiffs might not survive the schedule, which was true. They settled in 1928 for ten thousand dollars each and six hundred a year, and most of that money went on morphine.

Their testimony changed American labour law. The case established that a worker could sue an employer for an occupational disease with a long latency, and the standards written afterwards were still protecting people at Los Alamos twenty years later.`;

const EMU_BODY = `In November 1932 the Australian government sent the Seventh Heavy Battery of the Royal Australian Artillery to Campion, Western Australia, with two Lewis guns and ten thousand rounds, to deal with emus.

The birds had arrived in numbers after the harvest, roughly twenty thousand of them, flattening wheat that soldier-settlers had been given land to grow. Major G. P. W. Meredith (1893–1970) took command of an operation that was, on paper, straightforward.

The emus declined to behave like a target. They scattered on the first burst and learned within days to post sentinels, breaking into small groups that ran at thirty miles an hour and absorbed rifle fire without stopping. One gun jammed after twelve birds. An attempt to mount a Lewis gun on a truck ended with the gunner unable to aim on the terrain.

After six days and twenty-five hundred rounds, the official count was somewhere between fifty and five hundred birds, depending on who was asked. The operation was withdrawn, resumed under political pressure, and quietly ended.

Meredith later compared the emus favourably to Zulu infantry for their ability to take casualties and keep coming. The government went back to paying a bounty, which worked.`;

export const DRAFTS: Draft[] = [
  {
    id: 482,
    page_id: 1,
    source_item_id: 107,
    topic: null,
    status: "review",
    hook: "In 1925 Victor Lustig sold the Eiffel Tower for scrap metal. The buyer was too ashamed to report it — so Lustig came back a month later and sold it again.",
    caption:
      "🗼 The Eiffel Tower was only ever meant to stand for twenty years, and by 1925 the city was openly complaining about the cost of painting it.\n📰 Victor Lustig read that complaint in a newspaper and had ministry stationery forged the same week.\n🤝 He invited six scrap dealers to a confidential meeting and explained that the demolition contract could not be announced publicly.\n💰 André Poisson paid for the tower — and then paid a bribe on top, because that was how he expected the deal to work.\n🔁 Poisson was too ashamed to report it, so Lustig came back and ran the whole thing a second time.",
    first_comment: LUSTIG_BODY,
    highlight_phrases: ["1925", "Victor Lustig", "Eiffel Tower", "scrap metal", "sold it again"],
    hashtags: ["#history", "#historyretraced", "#eiffeltower", "#truecrime", "#1920s"],
    image_prompt:
      "Photorealistic documentary photograph, Paris 1925: a well-dressed man in a three-piece suit and homburg stands in a hotel suite, mid-conversation, papers spread on a walnut table. Medium close-up, natural window light, believable period dress, one readable face in the foreground. Keep the top-right quadrant clean.",
    hero_image_path: "heroes/482-lustig.png",
    composed_image_path: "composed/482-lustig.png",
    inset_image_path: "insets/482-lustig.png",
    inset_size_px: null,
    metricool_post_id: null,
    inset_x_ratio: null,
    inset_y_ratio: null,
    warnings: [],
    progress_step: null,
    progress_pct: 100,
    error: null,
    created_at: ago(1.5),
    updated_at: ago(1.4),
  },
  {
    id: 483,
    page_id: 1,
    source_item_id: 103,
    topic: null,
    status: "review",
    hook: "In 690 AD Wu Zetian declared herself Emperor of China. She was the only woman ever to hold the title, she took it at sixty-six, and she kept it for fifteen years.",
    caption:
      "🏯 Wu Zetian entered the palace at thirteen as a junior concubine, the lowest rank that came with a name.\n📜 When her first emperor died she was sent to a convent — and his son brought her back to court within two years.\n🩸 The histories accuse her of strangling her own daughter to frame a rival, and every one of them was written by men she had removed from office.\n⚖️ She ran the examination system on merit rather than birth, which cost the great families the posts they had assumed were theirs.\n🪦 Her tomb outside Xi'an carries a memorial tablet seven metres high, and it is completely blank.",
    first_comment: WU_BODY,
    highlight_phrases: [
      "690 AD",
      "Wu Zetian",
      "Emperor of China",
      "only woman",
      "sixty-six",
      "fifteen years",
    ],
    hashtags: ["#history", "#historyretraced", "#china", "#tangdynasty", "#womeninhistory"],
    image_prompt:
      "Photorealistic historical reenactment photograph, Tang dynasty China: an older woman in imperial court robes seated in a hall of carved timber, torchlight and shadow, mid-shot with the face clearly readable. Documentary tone, no fantasy, no glow. Keep the top-right quadrant clean.",
    hero_image_path: "heroes/483-wu.png",
    composed_image_path: "composed/483-wu.png",
    inset_image_path: "insets/483-wu.png",
    inset_size_px: null,
    metricool_post_id: null,
    inset_x_ratio: null,
    inset_y_ratio: null,
    warnings: [],
    progress_step: null,
    progress_pct: 100,
    error: null,
    created_at: ago(2.2),
    updated_at: ago(2.1),
  },
  {
    id: 484,
    page_id: 1,
    source_item_id: null,
    topic: "Hedy Lamarr and frequency hopping",
    status: "approved",
    hook: "In 1942 Hedy Lamarr patented the frequency-hopping system that Bluetooth and GPS still use. The Navy filed it away and told her to sell war bonds instead.",
    caption:
      "🎬 Hedy Lamarr was the most photographed face at MGM and the co-holder of US Patent 2,292,387 in the same year.\n💣 She learned about torpedo guidance at her first husband's arms-dealing dinners, where she was seated as decoration.\n🎹 Her co-inventor George Antheil solved the synchronisation problem with a slotted paper roll, borrowed from player pianos.\n🚫 The Navy shelved it and sent her on a bond tour, where she raised twenty-five million dollars.\n📶 The patent had expired by the time the principle turned up underneath Bluetooth and GPS.",
    first_comment: LAMARR_BODY,
    highlight_phrases: [
      "1942",
      "Hedy Lamarr",
      "frequency-hopping",
      "Bluetooth and GPS",
      "sell war bonds",
    ],
    hashtags: ["#history", "#historyretraced", "#hedylamarr", "#invention", "#wwii"],
    image_prompt:
      "Photorealistic photograph, 1940s Los Angeles: a woman at a drafting table in a domestic study, pencil in hand, technical diagrams under a desk lamp, warm practical lighting. Medium close-up, period dress, face readable. Keep the top-right quadrant clean.",
    hero_image_path: "heroes/484-lamarr.png",
    composed_image_path: "composed/484-lamarr.png",
    inset_image_path: "insets/484-lamarr.png",
    inset_size_px: null,
    metricool_post_id: null,
    inset_x_ratio: null,
    inset_y_ratio: null,
    warnings: [],
    progress_step: null,
    progress_pct: 100,
    error: null,
    created_at: ago(6),
    updated_at: ago(4),
  },
  {
    id: 485,
    page_id: 1,
    source_item_id: 102,
    topic: null,
    status: "rejected",
    hook: "In 1917 the Radium Girls were taught to point their brushes with their lips. The company called the paint harmless for seven more years.",
    caption:
      "⌚ The dial painters earned three times a normal factory wage, and the work was advertised as clean.\n💋 The company taught lip-pointing — roll the brush between your lips, dip, paint — several hundred times a day.\n🦴 Radium behaves like calcium, so the bones took it in and kept it.\n🩺 Dr Theodore Blum described a pattern of dying jawbones in 1924 that he had never seen before.\n⚖️ Five women sued in 1927, and their testimony rewrote American occupational disease law.",
    first_comment: RADIUM_BODY,
    highlight_phrases: ["1917", "Radium Girls", "with their lips", "harmless", "seven more years"],
    hashtags: ["#history", "#historyretraced", "#radiumgirls", "#labourhistory", "#1920s"],
    image_prompt:
      "Photorealistic documentary photograph, 1917 factory interior: young women in work smocks at a long bench painting watch dials, low window light, dust in the air. Mid-shot, two readable faces in the foreground. Keep the top-right quadrant clean.",
    hero_image_path: "heroes/485-radium.png",
    composed_image_path: "composed/485-radium.png",
    inset_image_path: null,
    inset_size_px: null,
    metricool_post_id: null,
    inset_x_ratio: null,
    inset_y_ratio: null,
    warnings: [],
    progress_step: null,
    progress_pct: 100,
    error: null,
    created_at: ago(27),
    updated_at: ago(25),
  },
  {
    id: 486,
    page_id: 1,
    source_item_id: 104,
    topic: null,
    status: "review",
    hook: "Before refrigeration, Boston sold winter. Frederic Tudor shipped lake ice to Calcutta in sawdust. Two thirds melted on the way, and he got rich on the rest.",
    caption:
      "🧊 Frederic Tudor's first ice cargo sailed in 1806, and nobody in the Caribbean knew what to do with it.\n🪵 Sawdust was the breakthrough — a waste product from Maine's mills that turned out to be an excellent insulator.\n🚢 A shipment to Calcutta took four months and crossed the equator twice.\n📉 Two thirds of every load melted, and the surviving third still undercut every local alternative.\n🏦 He was jailed for debt twice before the business made him one of Boston's richest men.",
    first_comment: null,
    highlight_phrases: ["Boston sold winter", "Frederic Tudor", "Calcutta", "sawdust", "Two thirds melted"],
    hashtags: ["#history", "#historyretraced", "#boston", "#trade", "#19thcentury"],
    image_prompt:
      "Photorealistic documentary photograph, New England 1840s: men in heavy coats cutting blocks of ice from a frozen lake with long saws, horses and sledges behind them, flat overcast winter light. Mid-shot, faces readable. Keep the top-right quadrant clean.",
    hero_image_path: null,
    composed_image_path: null,
    inset_image_path: null,
    inset_size_px: null,
    metricool_post_id: null,
    inset_x_ratio: null,
    inset_y_ratio: null,
    warnings: [],
    progress_step: "hero image",
    progress_pct: 45,
    error: "Gemini refused the image prompt: safety filter on `historical reenactment` (finish_reason=SAFETY). Text is written and saved — regenerate the image or edit the prompt.",
    created_at: ago(0.6),
    updated_at: ago(0.55),
  },
  {
    id: 487,
    page_id: 1,
    source_item_id: 106,
    topic: null,
    status: "review",
    hook: "In 1932 Australia sent artillery to fight twenty thousand emus. After six days and twenty-five hundred rounds, the army withdrew.",
    caption:
      "🦤 Twenty thousand emus walked into the Western Australian wheat belt after the 1932 harvest.\n🔫 The government's answer was the Seventh Heavy Battery, two Lewis guns and ten thousand rounds.\n🏃 The emus scattered on the first burst and learned to post sentinels within days.\n📊 Six days and twenty-five hundred rounds produced a body count nobody could agree on.\n🏳️ The operation was withdrawn, and the government went back to paying a bounty.",
    first_comment: EMU_BODY,
    highlight_phrases: ["1932", "Australia", "twenty thousand emus", "six days", "the army withdrew"],
    hashtags: ["#history", "#historyretraced", "#australia", "#emuwar", "#1930s"],
    image_prompt:
      "Photorealistic documentary photograph, Western Australia 1932: two soldiers in slouch hats beside a truck-mounted machine gun on cracked farmland, dry wheat stubble to the horizon, harsh midday sun. Mid-shot, faces readable. Keep the top-right quadrant clean.",
    hero_image_path: "heroes/487-emu.png",
    composed_image_path: "composed/487-emu.png",
    inset_image_path: null,
    inset_size_px: null,
    metricool_post_id: null,
    inset_x_ratio: null,
    inset_y_ratio: null,
    warnings: [
      "hook: opens with a question — the hook must not ask one (2 retries spent)",
      `first comment: ${EMU_BODY.length} characters, below the 1,500 minimum`,
    ],
    progress_step: null,
    progress_pct: 100,
    error: null,
    created_at: ago(3.1),
    updated_at: ago(3),
  },
];
