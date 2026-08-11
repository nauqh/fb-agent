import { ReviewList } from "@/components/review-list";
import { ScreenHeader } from "@/components/screen";

/**
 * The queue is the screen; the draft slides over it.
 *
 * The list lives in the layout rather than the page because Next keeps a layout
 * mounted across navigations between its children. Opening a draft therefore
 * does not remount the queue, so a row still generating keeps its poll running
 * while another one is edited — and the queue is still there, unscrolled, when
 * the sheet closes.
 */
export default function ReviewLayout({ children }: { children: React.ReactNode }) {
  return (
    // `pr-3`: this element owns the scrollbar, so without it the bar sits hard
    // against the table's right border and reads as part of the frame. The
    // padding is inside the scroll container, so it holds the content off the
    // bar rather than moving the bar.
    <div className="flex min-h-0 flex-1 flex-col overflow-y-auto pr-3">
      <ScreenHeader title="Review" />
      <ReviewList />
      {children}
    </div>
  );
}
