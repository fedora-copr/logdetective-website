(ns app.explain.atoms
  (:require [reagent.core :as r]))

(def current-hash-atom (r/atom "#copr"))
(def input-values (r/atom nil))
(def input-errors (r/atom []))
(def form (r/atom nil))
(def ai-gen-disclaimer (str "This explanation was provided by AI. Always review AI generated content prior to use."))
(def mission-statement-prompt
  (str
    "Improving RPM packaging experience by analyzing build "
    "logs and explaining the failure in simple words."))
