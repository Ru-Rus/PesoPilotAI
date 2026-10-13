import "./globals.css";
import { connection } from "next/server";
export const metadata = {
  title: "PesoPilot · Your money, in focus",
  description: "Personal finance dashboard for Philippine pesos",
};
export default async function Layout({
  children,
}: {
  children: React.ReactNode;
}) {
  await connection();
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
