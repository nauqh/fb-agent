# PRD: Website articles

- **Product**: fb-agent, website articles feature
- **Status**: Version 1 in build
- **Last updated**: 2026-10-12

## Summary

> **Auto-drafts write no articles for now** (client, 2026-10-12: not an
> official feature yet). Articles come only from Write article in the
> cart or on a draft. The auto-draft parts below describe the plan, and
> the code for them is in git history (`3bb4ccc` and before).

The politics Page's RSS auto-drafts pick news items whose full article the app
can read, and write two things from each: the Facebook post, as today, and a
full article for the client's WordPress site,
[thehouseofcommonsense.co.uk](https://thehouseofcommonsense.co.uk). The
operator reviews both in the draft drawer. Scheduling publishes the article and
adds its link to the post's first comment. Facebook brings the readers; the
website earns from them through ads.

## Problem and opportunity

- **Problem**: Facebook pays about $100 per million views. A Page with large
  reach still earns very little from the posts themselves.
- **Opportunity**: Readers who click through to the website see ads the client
  controls, which pay far more per view.
- **Solution**: The Facebook post hooks the reader. The full story lives on the
  website, linked from the first comment.

Facebook shows posts with a link in the body to fewer people. The link
therefore goes in the first comment, not in the post. A friend's Page already
works this way:
[example post](https://www.facebook.com/photo?fbid=1695364669262618&set=a.484235947042169).

## Order

Writing and going live run in opposite orders.

- **Writing: the post first, then the article**, in the same auto-draft run.
  There is never an article without a post.
- **Going live: the article first.** It is published when the operator
  schedules the post, so the link in the first comment works whenever the post
  goes out.

## Sources

Version 1 uses RSS only. A feed item carries a headline and a short summary,
about 200 characters. That is too thin for an article, so the app reads the
full article from the item's link itself, with the same reader the Web link
source uses.

Measured on 2026-10-10, four newest items per feed on the politics Page:

| Feed | Full text read | Length |
|---|---|---|
| BBC, Express, Mirror, Manchester Evening News, Birmingham Live, Metro, Guardian, Standard | 4 of 4 each | 1,700 to 12,000 characters |
| Sky News | 0 of 4 | Refused (403) |
| Google News (3 feeds) | 0 of 12 | Links are Google redirect pages |

The auto-draft skips any item it cannot read in full. The operator never sees
it.

## How it works

1. **Fetch the feeds.** Same as today's RSS auto-draft: unused items only.
2. **Rank them.** Same as today: Gemini picks the items that fit the Page's
   instructions, best first.
3. **Read the full article.** New. Going down the ranked list, the app reads
   each item's link and skips the ones it cannot read, until it has enough.
4. **Write the post** from the full text. Changed: today Gemini is handed only
   the link and reads it itself, which some publishers refuse.
5. **Write the article** from the same text. New.
6. **Review.** The draft drawer gets an Article tab: title and body, both
   editable. Rejecting the draft discards both.
7. **Schedule.** One action publishes the article to WordPress, sets the first
   comment to the Page's call to action with the link, and schedules the post.
   If WordPress fails, nothing is scheduled and the error is shown.

A post with an article has no written first comment: the comment is the call
to action and the link only (client, 2026-10-12). The call to action is set in
Settings, Writing, Article link; `{link}` marks where the link goes, and the
default is "Read the full story: {link}".

On Sources, the cart bar offers **Write article** for RSS items and web links on
the politics Page, ticked by default. A story the app cannot read still makes the
post, with a warning. Topic drafts, competitor posts, tweets and other Pages work
exactly as today.

A draft made without an article has a **Write article** button in the draft
drawer (client, 2026-10-12). The operator generates from headlines and decides
after reading the post. The button reads the full story if it has not been read,
writes the article, and drops the written first comment. A story that cannot be
read is refused with the reason.

## Users

- **The operator** reviews drafts and their articles, and schedules posts.
- **Facebook readers** see the post, open the comments and click through.

## Requirements

### Must have

| Feature | Acceptance criteria |
|---|---|
| Full-text pick | The politics Page's RSS auto-draft only writes from items whose full article could be read. Items that cannot be read are skipped, and the run notes how many. |
| Clean source text | The reader drops what is not the story: related-story headlines, newsletter sign-up text and similar page furniture. |
| Article writing | Written in the same run as the post, from the same full text, with a title, in the Page's voice. It uses the source's facts only and never copies its sentences. Its length follows the source, roughly 400 to 900 words, and is never padded. |
| Article format | The body is HTML in the theme's layout: `h3` subheadings, quotes in `blockquote`, and bullet lists where the facts suit them. |
| Article review | The draft drawer has an Article tab with the title and the HTML body, both editable. Save, Revert and the unsaved-changes check cover it. |
| Publish and schedule | Scheduling a draft with an article publishes it to WordPress with its title, body and featured image, then schedules the post with the Page's call to action and the article's link as the whole first comment. |
| Call to action | Settings has an Article link field on the politics Page. `{link}` is replaced by the article's address; without it the link goes last. Blank is the default. |
| Article prompt | The article prompt is editable per Page, like the other prompts, and a post style may carry its own. A blank style field uses the Page's. |
| Write article on a draft | The drawer offers Write article on a draft from an RSS item or web link that has no article and is not scheduled. |
| Link works at publish time | The article is live before the post is handed to Metricool. A post MUST NOT go out linking to a missing page. |
| Failure is visible | If the article cannot be written, the post is still made and the draft says so. If WordPress refuses, the post is not scheduled and the error is shown. |

### Out of scope for version 1

- Articles from topic drafts, competitor posts or tweets.
- Pages other than politics.
- Per-feed full-text checks and marks on sources.
- A Rewrite button for the article.
- The link in the Facebook preview, and "View article" links elsewhere.
- WordPress categories and tags.
- Scheduling the article in WordPress for the post's time (`future`). Version 1
  publishes immediately.
- Unpublishing. An article stays live if its post is unscheduled or deleted; it
  is removed by hand in WordPress.
- A Settings screen for the site. It is configuration, in the server's
  environment.
- Articles built from several sources on the same story. This is the way to
  longer articles without invented facts.
- Ads setup, site design and theme changes. The client handles these.

## Technical approach

- **Reader**: `api/app/sources/web.py`, used today for the Web link source.
- **WordPress REST API**: `POST /wp-json/wp/v2/posts` with `status: publish`,
  and `POST /wp-json/wp/v2/media` for the featured image. The link for the
  first comment is read from WordPress's response, since a draft has no final
  URL.
- **Authentication**: a WordPress Application Password in the server's
  environment, never in the browser. The site must be on HTTPS before
  WordPress offers one. The admin login password is not used by the app.
- **Metricool is unchanged.** The first comment is still plain text; for a
  post with an article it is the call to action and a URL. The planner stays the source of truth for scheduled posts.
- **Writer**: the article is one extra Gemini call after the post, with its own
  prompt, `article.txt`, overridable per Page and per post style like the
  others.
- **Images**: the featured image is the post's hero image, without the overlay
  text.

## Success metrics

- **Primary**: clicks from Facebook to the website, per post. WordPress or
  Google Analytics reports this.
- **Secondary**: website ad revenue per month, against Facebook payout for the
  same Page.
- **Reliability**: every scheduled post with an article links to a live page.
  Zero broken links.

## Open questions

1. Should the demo content be deleted before the first real article goes up?
2. Please switch the site to HTTPS, create a WordPress Application Password for
   the app, and change the admin password that was shared over chat.
