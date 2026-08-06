import type { Draft } from "@/lib/types";

/**
 * What the fake writer returns.
 *
 * The run has to put *something* in the row, and placeholder text would defeat
 * the reason the fixtures are real: a Draft the operator cannot plausibly read
 * does not test the Review layout. Three written outputs, matched to Source
 * Items by `external_id` where one fits and cycled otherwise.
 */
export type WrittenDraft = Pick<
  Draft,
  | "hook"
  | "caption"
  | "first_comment"
  | "highlight_phrases"
  | "hashtags"
  | "image_prompt"
>;

const THARP_BODY = `Marie Tharp (1920–2006) arrived at Columbia's Lamont Geological Observatory in 1948 with degrees in geology and mathematics, at a moment when the war had briefly made it possible for a woman to hold both.

She was not permitted aboard the research ships. Women were considered bad luck at sea, and the soundings she worked from were collected by Bruce Heezen (1924–1977), who sailed and sent back the echo-sounder rolls. Tharp's job was to turn columns of depth readings into a picture, which she did by hand, plotting profile after profile across the North Atlantic in ink.

The valley showed up almost immediately. Running down the centre of the mid-ocean ridge, in every profile she drew, was a deep notch — a rift, continuous, thousands of miles long. If the sea floor was splitting apart along that line, then continental drift was not the discredited idea her generation had been taught to dismiss. It was happening, and here was the seam.

Heezen's response, which Tharp recorded without much comment, was that it was girl talk. He made her redo the work. She redid it, and the valley was still there.

What settled it was a second map in the same office plotting earthquake epicentres in the Atlantic. Laid over Tharp's rift, the epicentres fell inside it. Two independent datasets had drawn the same line, and the line meant the sea floor was spreading.

Their physiographic maps, painted by Heinrich Berann and published by National Geographic in 1977, put the ocean floor in front of the public for the first time. Tharp's name was not on the early papers that mattered most. She was given Lamont's Heritage Award in 2001, at eighty-one, five years before she died.`;

const KIRUNA_BODY = `Kiruna sits above the largest underground iron ore mine in the world, and in 2004 the mining company LKAB told the town what everyone had suspected for a decade: the ore body runs diagonally beneath the settlement, and following it would cause the ground under the town centre to deform.

The options were to stop mining or to move the town. Kiruna exists because of the mine — the settlement was founded in 1900 to work it, and the ore still pays for nearly everything — so the town voted to move.

Not to rebuild. To move. Around twenty of the oldest and most-loved buildings were lifted whole and driven three kilometres east on self-propelled modular transporters, at a walking pace, along roads widened for the purpose. Kiruna Church, a timber building from 1912 shaped like a Sami tent and voted Sweden's most beautiful, was cut into two pieces and made the journey in 2025, with the whole town walking behind it.

The clock tower from the old town hall came down and went back up on the new square. Houses that could not be moved were photographed, measured and replaced. Around six thousand people — a third of the population — had to be rehoused, and the compensation formula argued over in public for years.

The new centre opened in stages from 2022. The old one is being demolished behind a fence that moves closer each year, and the buildings that remain there are counted down publicly. Residents describe visiting streets they grew up on that now end in a barrier, with the ground on the other side already sinking.`;

const EILEAN_MOR_BODY = `On 15 December 1900 the steamer Archtor passed the Flannan Isles and noted that the light on Eilean Mor was dark. The report was not acted on for eleven days.

When the relief vessel Hesperus reached the island on 26 December, no flag flew, no boxes were waiting on the landing, and nobody answered the whistle. Joseph Moore went up to the lighthouse alone and found the gate shut, the door closed, the beds unmade, and the clock stopped.

The three keepers were James Ducat (1857–1900), Thomas Marshall (1860–1900) and Donald MacArthur (1860–1900). The lamp was cleaned and refilled, ready to light. The last log entry was for 15 December. Two sets of oilskins were gone from their hooks and one was still hanging, which is the detail the story has never let go of: whatever happened, one man went out into it without his coat.

The west landing, a hundred and ten feet above the sea, was wrecked. A supply box fixed to the rock at that height had been torn away, iron railings were bent flat, and a block of stone weighing more than a ton had been shifted. The relieving keeper's report concluded that a wave had done it.

The official finding was that the men had gone down to secure equipment during a storm and been taken by the sea. It is the only explanation that fits the damage, and it requires all three to have been at the landing at once, which the standing orders forbade.

Robert Muirhead, who had hired all three, wrote the investigation and was careful in it. The story that the log recorded days of screaming and weeping was invented decades later by a poem and then repeated as fact.`;

export const WRITTEN: WrittenDraft[] = [
  {
    hook: "Marie Tharp mapped the Atlantic sea floor by hand and found a rift valley that proved continental drift. She was told it was girl talk and made to draw it twice.",
    caption:
      "🗺️ Marie Tharp turned columns of echo-sounder readings into the first picture of the ocean floor, profile by profile, in ink.\n🚢 She was not allowed on the research ships — the data came back to her in rolls from someone else's voyage.\n🏔️ A continuous rift valley appeared down the centre of the mid-Atlantic ridge, thousands of miles long.\n😤 Bruce Heezen called it girl talk and made her redo the work; the valley was still there.\n🌍 An earthquake map in the same office fell exactly inside her rift, and continental drift stopped being a joke.",
    first_comment: THARP_BODY,
    highlight_phrases: [
      "Marie Tharp",
      "by hand",
      "rift valley",
      "continental drift",
      "girl talk",
      "draw it twice",
    ],
    hashtags: ["#history", "#historyretraced", "#marietharp", "#geology", "#womeninscience"],
    image_prompt:
      "Photorealistic documentary photograph, 1950s research office: a woman leaning over a vast hand-drawn ocean chart on a drafting table, dividers in hand, angled desk lamp, paper rolls stacked behind her. Medium close-up, face readable, natural light. Keep the top-right quadrant clean.",
  },
  {
    hook: "Sweden is moving an entire town. Kiruna sits on an iron mine that is swallowing it, so the buildings are being driven three kilometres east at walking pace.",
    caption:
      "⛏️ Kiruna sits on the largest underground iron ore mine in the world, and the ore runs directly beneath the town centre.\n🏘️ In 2004 the choice was to stop mining or move the settlement, and the town voted to move.\n🚚 Around twenty of the oldest buildings were lifted whole and driven east on modular transporters.\n⛪ Kiruna Church, voted Sweden's most beautiful building, was cut in two and moved in 2025 with the town walking behind it.\n🚧 The old centre is being demolished behind a fence that moves closer every year.",
    first_comment: KIRUNA_BODY,
    highlight_phrases: [
      "moving an entire town",
      "Kiruna",
      "iron mine",
      "three kilometres east",
      "walking pace",
    ],
    hashtags: ["#history", "#historyretraced", "#kiruna", "#sweden", "#engineering"],
    image_prompt:
      "Photorealistic documentary photograph, northern Sweden: a large timber building on a modular transporter moving along a widened road through snow-lined terrain, workers in high-visibility jackets walking alongside. Mid-shot, flat overcast arctic light, faces readable. Keep the top-right quadrant clean.",
  },
  {
    hook: "In December 1900 three keepers vanished from Eilean Mor. The lamp was ready, the clock had stopped, and one oilskin coat was still on its hook.",
    caption:
      "🌊 A passing steamer noted the Flannan Isles light was dark on 15 December 1900, and nothing was done for eleven days.\n🚪 The relief keeper found the gate shut, the door closed, the beds unmade and the clock stopped.\n🧥 Two sets of oilskins were gone and one was still on its hook — the detail the story has never let go of.\n🪨 The west landing, a hundred and ten feet up, was wrecked, with a one-ton block shifted and iron railings bent flat.\n📖 The screaming and weeping in the logbook were invented by a poem decades later.",
    first_comment: EILEAN_MOR_BODY,
    highlight_phrases: [
      "December 1900",
      "three keepers",
      "Eilean Mor",
      "the clock had stopped",
      "still on its hook",
    ],
    hashtags: ["#history", "#historyretraced", "#flannanisles", "#unsolved", "#scotland"],
    image_prompt:
      "Photorealistic documentary photograph, remote Scottish island 1900: a stone lighthouse on a cliff under heavy grey weather, a keeper in oilskins on the path below, sea spray at the landing. Mid-shot with one readable figure in the foreground, natural storm light. Keep the top-right quadrant clean.",
  },
];

/**
 * Source Items that have a written output waiting for them, so ticking the
 * Marie Tharp article and generating produces the Marie Tharp draft rather than
 * whatever came next in the rotation.
 */
export const WRITTEN_BY_EXTERNAL_ID: Record<string, number> = {
  "https://www.smithsonianmag.com/history/the-woman-who-mapped-the-ocean-floor-180987410/": 0,
  "https://www.atlasobscura.com/articles/the-village-that-moved-itself-uphill": 1,
  "https://allthatsinteresting.com/the-lighthouse-keepers-of-eilean-mor": 2,
};
