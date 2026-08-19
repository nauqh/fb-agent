# Competitor post image as Gemini vision input — note

**Status:** note for later work. Findings from the old app
(`D:\Laboratory\social-agent`, branch `feature/migrate-to-new-deployment`,
read-only), plus plan.

## Question asked

Did the old app use the image from a competitor post as input?

## Answer

Yes — but only as **vision input to Gemini**, never as the output image.

- `src/services/facebookGenerateGraph.ts:464-467` (`writeThreeDraftsNode`)
  fetches the competitor post's `picture_url` and attaches it to the Gemini
  call as an `inlineData` image Part, alongside the caption text:

  ```ts
  // Only competitor posts (not saved-viral) send their image to Gemini.
  const isCompetitorSource =
    post != null && state.competitorPostIds.includes(post.id);
  const imagePart =
    isCompetitorSource && post?.picture_url
      ? await fetchGeminiImagePart(post.picture_url)
      : null;
  ```

- `src/services/facebookGenerateGraph.ts:144-145` sends it in the same user
  message as the text prompt:

  ```ts
  contents = [{ role: "user", parts: [{ text: prompt }, ...options.imageParts] }]
  ```

- Same pattern in `src/services/facebookTopicSuggestService.ts:56`
  (`suggestTopicFromPosts`) — source-post images fed to Gemini vision for topic
  suggestion, capped at `MAX_IMAGES`.

## Image-fetch mechanics (old app)

`src/lib/gemini/fetch-image-part.ts`:

- Plain `fetch(url)` with a browser-ish `User-Agent` header — publisher CDNs
  behind RSS articles routinely 403 anonymous requests. Omitting the UA
  silently loses the image for exactly the sources that need it.
- Constraints: image `<= 4MB` (`MAX_IMAGE_BYTES`), mime in
  `png|jpeg|jpg|webp|gif`. Empty body or any fetch failure → `null`.
- Callers treat `null` as "fall back to text-only", never as an error.

## What the image is NOT used for

- Not reused as the draft's final image. Output image is generated separately:
  `buildFacebookImageUserPrompt` → Gemini hero image → compositor
  (text panel + logo watermark) → `attachDraftImageAsync`.
- Not sent for saved-viral / library sources — gated to competitor posts only.

## Plan

Follow the old mechanics in the new app (`fb-agent`):

1. Agent must read the competitor post image (vision input) alongside the
   caption text when writing drafts.
2. Same gating intent: image input for competitor posts; library/viral posts
   text-only unless a reason appears.
3. Keep the graceful fallback: any fetch/mime/size failure → text-only path,
   no error surfaced to the user.
4. Output image stays a separate generated asset; competitor image is input
   only.
