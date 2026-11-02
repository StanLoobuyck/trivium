// Hash routes → screens. A new screen = one module in screens/ + one line here.
import { closeMenus, scroller, setBarTitle, stopPoll } from "./ui.js";
import { drawChrome, ensureSideData } from "./sidebar.js";
import { renderAdd } from "../screens/add.js";
import { renderArchive } from "../screens/archive.js";
import { renderDashboard } from "../screens/dashboard.js";
import { renderLecture } from "../screens/lecture.js";
import { renderSetup } from "../screens/setup.js";

export async function route() {
  stopPoll();
  closeMenus();
  const [, page, arg, tab] = location.hash.split("/");
  document.body.dataset.page = page || "home";
  scroller().scrollTop = 0;
  drawChrome();
  setBarTitle();
  document.getElementById("bar-actions").innerHTML = "";
  if (page === "lecture" && arg) { ensureSideData(); return renderLecture(decodeURIComponent(arg), tab); }
  if (page === "setup") { ensureSideData(); return renderSetup(); }
  if (page === "add") { ensureSideData(); return renderAdd(); }
  if (page === "archive") { ensureSideData(); return renderArchive(); }
  if ((page === "c" || page === "f") && arg) return renderDashboard(`${page}:${decodeURIComponent(arg)}`);
  return renderDashboard("", page === "progress" ? "progress" : null);
}
window.addEventListener("hashchange", route);
