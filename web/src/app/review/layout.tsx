import { ReviewList } from "@/components/review-list";
import { ScreenHeader } from "@/components/screen";

/**
 * The list lives in the layout, not the page.
 *
 * Next keeps a layout mounted across navigations between its children, so
 * selecting a different Draft does not remount the queue — which means a row
 * still generating keeps its poll running while the operator edits another one.
 */
export default function ReviewLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <ScreenHeader title="Review" />
      <div className="grid min-h-0 flex-1 gap-6 lg:grid-cols-[300px_minmax(0,1fr)]">
        <div className="min-h-0 lg:h-full">
          <ReviewList />
        </div>
        {/* The detail pane is its own scroll container, so a 2,000-character
            first comment does not move the queue beside it. */}
        <div className="min-h-0 lg:overflow-y-auto">{children}</div>
      </div>
    </div>
  );
}
