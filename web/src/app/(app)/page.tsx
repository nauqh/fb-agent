import { redirect } from "next/navigation";

/** The operator loop starts at Sources; there is no dashboard to land on. */
export default function Home() {
  redirect("/sources");
}
