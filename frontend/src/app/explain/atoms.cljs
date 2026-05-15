(ns app.explain.atoms
  (:require [reagent.core :as r]))

(def current-hash-atom (r/atom "#copr"))
(def input-values (r/atom nil))
(def input-errors (r/atom []))
