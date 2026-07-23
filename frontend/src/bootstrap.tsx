import { createRoot } from "react-dom/client";
import Root from "./main";

const container = document.getElementById("root");
if (!container) throw new Error("缺少应用根节点");
createRoot(container).render(<Root />);
