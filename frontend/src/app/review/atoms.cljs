(ns app.review.atoms
  (:require
   [reagent.core :as r]))

(def files (r/atom nil))
(def error-description (r/atom nil))
(def error-title (r/atom nil))
(def status (r/atom nil))

(def form
  (r/atom {:fas nil
           :how-to-fix nil
           :fail-reason nil}))

(def votes
  (r/atom {:how-to-fix 0
           :fail-reason 0}))
