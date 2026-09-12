import { redirect } from "next/navigation";

/** The operator opens on the Page's numbers; Sources is one rail item away. */
export default function Home() {
  redirect("/overview");
}
