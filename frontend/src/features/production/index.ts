import type { FeatureDescriptor } from "../types";

export const feature: FeatureDescriptor = {
  id: "production",
  title: "标准制作包",
  owner: "EXE-07",
  status: "planned",
  routes: ["/content/projects"],
  note: "首期不交付。按 UX-04R 终审规则，不得出现空导航，因此这条路径不进导航、直接走 404 恢复页。"
};
