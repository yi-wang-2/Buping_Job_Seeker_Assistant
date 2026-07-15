import { cp, mkdir, readFile, readdir, rename, rm, writeFile } from "node:fs/promises";

await mkdir("dist/client", { recursive: true });
await rename("dist/index.html", "dist/client/index.html");
await rename("dist/assets", "dist/client/assets");
for (const entry of await readdir("dist", { withFileTypes: true })) {
  if (["client", "server", ".openai"].includes(entry.name)) continue;
  await rename(`dist/${entry.name}`, `dist/client/${entry.name}`);
}

await mkdir("dist/server", { recursive: true });
await cp("server/index.js", "dist/server/index.js");

await mkdir("dist/.openai", { recursive: true });
const hosting = await readFile(".openai/hosting.json", "utf8");
await writeFile("dist/.openai/hosting.json", hosting);
await cp("drizzle", "dist/.openai/drizzle", { recursive: true });

await rm("dist/.vite", { recursive: true, force: true });
