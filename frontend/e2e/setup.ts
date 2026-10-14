import { execFileSync } from "node:child_process";
import path from "node:path";
export default function setup() {
  const root = path.resolve(process.cwd(), "..");
  const python =
    process.platform === "win32"
      ? path.join(root, "backend/.venv/Scripts/python.exe")
      : path.join(root, "backend/.venv/bin/python");
  execFileSync(python, ["e2e_fixture.py", "setup"], {
    cwd: path.join(root, "backend"),
    stdio: "pipe",
  });
}
