import { existsSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";

const isFile = path => {
  if (!path || !existsSync(path)) return false;
  try {
    return statSync(path).isFile();
  } catch {
    return false;
  }
};

export const resolveChromePath = ({
  configured,
  cacheRoot = "/home/faye/diyu-build/cache/chrome-for-testing"
} = {}) => {
  const cached = existsSync(cacheRoot)
    ? readdirSync(cacheRoot, { withFileTypes: true })
        .filter(entry => entry.isDirectory())
        .map(entry => entry.name)
        .sort((left, right) =>
          right.localeCompare(left, undefined, { numeric: true })
        )
        .map(version => join(cacheRoot, version, "chrome-linux64", "chrome"))
    : [];
  return [
    configured,
    ...cached,
    "/usr/bin/google-chrome",
    "/usr/bin/chromium",
    "/home/faye/.cache/puppeteer/chrome/linux-148.0.7778.97/chrome-linux64/chrome"
  ].find(isFile);
};
