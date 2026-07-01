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

(defn handle-http-error [error]
  (let [http-status (:status error)
        status-text (:status-text error)
        detail (get-in error [:response :description])
        title (str http-status " " status-text)]
    (cond
      (= http-status 0)
      (handle-backend-error
       "No response"
       "The server did not respond. Please check your connection and try again.")

      detail
      (handle-backend-error title detail)

      :else
      (handle-backend-error title "An unexpected error occurred."))))

(defn handle-validation-error [title description]
  ;; Go back to "has files" state, let users fix
  ;; validation errors
  (reset! status nil)
  (reset! error-title title)
  (reset! error-description description))
