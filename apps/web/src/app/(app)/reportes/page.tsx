import { redirect } from "next/navigation";

// Sección retirada: los documentos de cada 8D están en su pestaña «Documentos y archivos».
export default function Page() {
  redirect("/casos");
}
