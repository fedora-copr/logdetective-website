(ns app.homepage
  (:require [reagent.core :as r]
            [clojure.string :as str]
            [cljs.source-map.base64 :as base64 :refer [encode]]
            [cljs.core.match :refer-macros [match]]))


(def input-id (r/atom nil))
(def input-chroot (r/atom nil))
(def current-hash-atom (r/atom nil))


(defn current-hash []
  (. (. js/document -location) -hash))

(defn homepage-submit []
  (let [source (str/replace @current-hash-atom "#" "")
        input (if (not= source "url") @input-id (js/btoa @input-id))
        url (str/join "/" ["/contribute" source input @input-chroot])]
    (set! (.-href (.-location js/window)) url)))

(defn on-tab-click [href]
  (reset! current-hash-atom href)
  (reset! input-id ""))

(defn on-input-id-change [target]
  (reset! input-id (.-value target)))

(defn on-input-chroot-change [target]
  (reset! input-chroot (.-value target)))

(defn render-navigation-item [title href]
  (let [active? (= href @current-hash-atom)]
    [:li {:class "nav-item ml-auto"}
     [:a {:class ["nav-link" (if active? "active" nil)]
          :href href
          :on-click #(on-tab-click href)}
      title]]))

(defn render-navigation []
   [:div {:class "card-header"}
    [:ul {:class "nav nav-tabs card-header-tabs"}
     (render-navigation-item "Copr" "#copr")
     (render-navigation-item "Koji" "#koji")
     (render-navigation-item "Packit" "#packit")
     (render-navigation-item "URL" "#url")]])

(defn render-card [provider url title img text placeholder & chroot?]
  [:div {:class "card-body"}
   [:div {:class "row"}
    [:div {:class "col-2"}
     [:a {:href url :title (if provider (str "Go to " provider) nil)}
      [:img {:src img, :class "card-img-top", :alt "..."}]]]

    [:div {:class "col-8"}
     [:h2 {:class "card-title"} title]
     [:p {:class "card-text"} text]

     ;; We do some ugly shenanigans with the position of the submit button
     ;; depending on how many inputs we have. Also the chroot input is kinda
     ;; hardcoded for Copr. We should do it more inteligently.
     (let [submit [:button
                   {:class "btn btn-outline-primary",
                    :type "button", :id "button-addon2"
                    :on-click #(homepage-submit)}
                   "Let's go"]]
       [:<>
        [:div {:class "input-group mb-3 container"}
         [:input
          {:type "text",
           :class "form-control",
           :placeholder placeholder
           :value @input-id
           :on-change #(on-input-id-change (.-target %))}]
         (when-not chroot? submit)]

        (when chroot?
          [:div {:class "input-group mb-3 container"}
           [:input
            {:type "text",
             :class "form-control",
             :placeholder "Chroot name, e.g. fedora-rawhide-x86_64"
             :value @input-chroot
             :on-change #(on-input-chroot-change (.-target %))}]
           submit])])]

    [:div {:class "col-2"}]]])

(defn render-copr-card []
  (render-card
   "Copr"
   "https://copr.fedorainfracloud.org"
   "Submit logs from Copr"
   "img/copr-logo.png"
   "Specify a Copr build ID and we will fetch and display all relevant logs."
   "Copr build ID, e.g. 6302362"
   true))

(defn render-packit-card []
  (render-card
   "Packit"
   "https://dashboard.packit.dev"
   "Submit logs from Packit"
   "img/packit-logo.png"
   (str/join "" ["Specify a Packit job ID, we will match it to a build, "
                 "fetch, and display all relevant logs."])
   "Packit job ID, e.g. 1015788"))

(defn render-koji-card []
  (render-card
   "Koji"
   "https://koji.fedoraproject.org"
   "Submit logs from Koji"
   "img/koji-logo.png"
   "Specify a Koji build ID to fetch and display all relevant logs."
   "Koji build ID, e.g. 2274591"))

(defn render-url-card []
  (render-card
   nil
   nil
   "Submit logs from URL"
   "img/url-icon.png"
   (str/join "" ["Paste an URL to a log file, or a build in some build system. "
                 "If recognized, we will fetch and display all relevant logs."])
   "https://paste.centos.org/view/raw/5ba21754"))

(defn render-cards []
  (match @current-hash-atom
         "#copr"   (render-copr-card)
         "#packit" (render-packit-card)
         "#koji"   (render-koji-card)
         "#url"    (render-url-card)
         :else     (render-copr-card)))

(defn homepage []
  (reset! current-hash-atom
          (if (str/blank? (current-hash)) "#copr" (current-hash)))
  [:div {:class "card text-center"}
   (render-navigation)
   (render-cards)])
