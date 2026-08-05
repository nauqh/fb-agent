import { cn } from "@/lib/utils";

/**
 * An indeterminate progress bar. No percentage, on purpose.
 *
 * A Metricool sync is one opaque request — 1.6MB and ~5.5s on a good day, with
 * nothing reported in between. A bar that eased to 90% and then sat there would
 * be inventing a number the server never sent, and it lies loudest exactly when
 * the vendor is slow and the operator most wants to know what is happening.
 *
 * Left indeterminate, the bar says only what is true: work is in flight. The
 * elapsed seconds beside it carry the rest.
 */
function Progress({ className, ...props }: React.ComponentProps<"div">) {
  return (
    // No `aria-valuenow`: its absence is what makes a progressbar indeterminate
    // to a screen reader, rather than a bar stuck at zero.
    <div
      role="progressbar"
      aria-busy="true"
      data-slot="progress"
      className={cn("relative h-1 w-full overflow-hidden rounded-full bg-muted", className)}
      {...props}
    >
      <div className="absolute inset-y-0 w-1/3 animate-progress-sweep rounded-full bg-primary" />
    </div>
  );
}

export { Progress };
