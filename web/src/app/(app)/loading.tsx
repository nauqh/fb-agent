import { Loading as LoadingState } from "@/components/loading";

/** Keeps the signed-in shell visible while a route segment is being rendered. */
export default function Loading() {
  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <LoadingState label="Loading screen" className="flex-1" />
    </div>
  );
}
