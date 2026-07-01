(ns app.core
  "This namespace contains your application and is the entrypoint for 'yarn start'."
  (:require [reagent.core :as r]
            [app.contribute.landing :refer [contribute-landing init-contribute-landing]]
            [app.contribute.core :refer [contribute init-data]]
            [app.review.core :refer [review init-data-review]]
            [app.explain.core :refer [explain-page init-explain]]))

(def routes
  "Map of DOM element IDs to their view components and init functions.
   The backend template determines which element exists on the page."
  {"app-homepage"           {:view explain-page    :init init-explain}
   "app-contribute-landing" {:view contribute-landing :init init-contribute-landing}
   "app-contribute"         {:view contribute      :init init-data}
   "app-review"             {:view review          :init init-data-review}
   "app-explain"            {:view explain-page    :init init-explain}})

(defn find-active-route
  "Find the first route whose DOM element exists on the page."
  []
  (->> routes
       (filter (fn [[id]] (.getElementById js/document id)))
       first))

(defn ^:dev/after-load render
  "Render the active route's view. Called on hot-reload without re-running init."
  []
  (when-let [[id {:keys [view]}] (find-active-route)]
    (r/render [view] (.getElementById js/document id))))

(defn ^:export main
  "Application entrypoint. Runs init for the active route, then renders."
  []
  (when-let [[_ {:keys [init]}] (find-active-route)]
    (when init (init)))
  (render))
