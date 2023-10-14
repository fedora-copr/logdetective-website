(ns app.editor.core
  (:require [reagent.core :as r]))


(def active-file (r/atom 0))


(defn tab [name key active?]
  [:li {:class "nav-item" :key key}
   [:a {:class ["nav-link" (if active? "active" nil)]
        :on-click #(reset! active-file key)
        :href "#"}
    name]])

(defn tabs [files]
  [:ul {:class "nav nav-tabs"}
   (doall (for [[i file] (map-indexed list files)
                :let [name (:name file)
                      active? (= name (:name (get files @active-file)))]]
            (tab name i active?)))])

(defn textarea [text]
  [:pre {:id "log" :class "overflow-auto"
         :dangerouslySetInnerHTML {:__html text}}])

(defn editor [files]
  [:<>
   (tabs files)
   (let [content (:content (get files @active-file))]
     (textarea content))])
