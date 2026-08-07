import type { FeatureDescriptor } from "../types";

/** `/user`. Today it is the entry shell; EXE-03 turns it into the workbench. */
export const feature: FeatureDescriptor = {
  id: "today",
  title: "今天可以做什么",
  owner: "EXE-03",
  status: "delivered",
  routes: ["/user"]
};
