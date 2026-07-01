(ns app.core
  "This namespace contains your application and is the entrypoint for 'yarn start'."
  (:require [reagent.core :as r]
            [app.contribute.landing :refer [contribute-landing init-contribute-landing]]
            [app.contribute.core :refer [contribute init-data]]
            [app.review.core :refer [review init-data-review]]
            [app.explain.core :refer [explain-page init-explain]]))

(def routes
  [["app-homepage" explain-page init-explain]
   ["app-contribute-landing" contribute-landing init-contribute-landing]
   ["app-contribute" contribute init-data]
   ["app-review" review init-data-review]
   ["app-explain" explain-page init-explain]])

(defn ^:dev/after-load render
  "Re-render after hot-reload. Does NOT re-run init to avoid duplicate requests."
  []
  (let [route (->> routes
                   (filter (fn [x] (.getElementById js/document (first x))))
                   first)
        name (nth route 0)
        view (nth route 1)]
    (r/render [view] (.getElementById js/document name))))

(defn ^:export main
  "Run application startup logic."
  []
  (let [route (->> routes
                   (filter (fn [x] (.getElementById js/document (first x))))
                   first)
        init (nth route 2)]
    (when init (init)))
  (render))
