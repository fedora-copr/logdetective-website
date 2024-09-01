(ns app.core
  "This namespace contains your application and is the entrypoint for 'yarn start'."
  (:require [reagent.core :as r]
            [app.homepage :refer [homepage fetch-stats-backend]]
            [app.contribute :refer [contribute init-data]]
            [app.review.core :refer [review init-data-review]]
            [app.prompt.core :refer [prompt]]))

(defn ^:dev/after-load render
  "Render the toplevel component for this app."
  []
  ;; This is not the standard way of doing this, we should probably use some
  ;; router. But it is good enough for now.
  (let [routes [["app-homepage" homepage fetch-stats-backend]
                ["app-contribute" contribute init-data]
                ["app-review" review init-data-review]
                ["app-prompt" prompt nil]]
        route (->> routes
                   (filter (fn [x] (.getElementById js/document (first x))))
                   first)
        name (nth route 0)
        view (nth route 1)
        init (nth route 2)]
    (when init (init))
    (r/render [view] (.getElementById js/document name))))

(defn ^:export main
  "Run application startup logic."
  []
  (render))
