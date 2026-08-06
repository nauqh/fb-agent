import { DraftSheet } from "@/components/draft-sheet";

/**
 * `params` is a Promise in Next 16 — synchronous access was removed. The page
 * awaits it and hands the id to the client component that does the polling.
 */
export default async function ReviewDetailPage({ params }: PageProps<"/review/[id]">) {
  const { id } = await params;
  return <DraftSheet draftId={Number(id)} />;
}
