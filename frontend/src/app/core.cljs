(ns app.core
  "This namespace contains your application and is the entrypoint for 'yarn start'."
  (:require [reagent.core :as r]
            [app.homepage :refer [homepage]]
            [app.contribute :refer [contribute init-data]]))


(defn ^:dev/after-load render
  "Render the toplevel component for this app."
  []
  ;; This is not the standard way of doing this, we should probably use some
  ;; router. But it is good enough for now.
  (cond (.getElementById js/document "app-homepage")
        (r/render [homepage] (.getElementById js/document "app-homepage"))

        (.getElementById js/document "app-contribute")
        (do
          (init-data)
          (r/render [contribute] (.getElementById js/document "app-contribute")))))

(defn ^:export main
  "Run application startup logic."
  []
  (render))
