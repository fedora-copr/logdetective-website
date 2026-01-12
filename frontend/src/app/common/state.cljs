(ns app.common.state
  (:require
   [reagent.core :as r]))

(def how-to-fix (r/atom nil))
(def fail-reason (r/atom nil))
(def files (r/atom nil))
(def error-description (r/atom nil))
(def error-title (r/atom nil))
(def status (r/atom nil))

(defn handle-backend-error [title description]
  (reset! status "error")
  (reset! error-title title)
  (reset! error-description description))

(defn handle-validation-error [title description]
  ;; Go back to "has files" state, let users fix
  ;; validation errors
  (reset! status nil)
  (reset! error-title title)
  (reset! error-description description))
