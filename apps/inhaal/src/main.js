import "@studie/design/tokens.css";
import "@studie/design/components.css";
import { lang } from "./i18n/index.js";
import { renderOverview } from "./screens/overview.js";

document.documentElement.lang = lang;
renderOverview(document.getElementById("app"));
