(ns app.common.provider-forms)

(defn on-input-change-handler [target input-values-atom]
  (swap! input-values-atom assoc
         (keyword (.-name target))
         (.-value target)))

(defn render-navigation-item [title href current-hash-atom on-tab-click-fn]
  (let [active? (= href @current-hash-atom)]
    [:li {:class "nav-item ml-auto"}
     [:a {:class ["nav-link" (if active? "active" nil)]
          :href href
          :on-click #(on-tab-click-fn href)}
      title]]))

(defn render-navigation [tabs current-hash-atom on-tab-click-fn]
  [:div {:class "card-header"}
   [:ul {:class "nav nav-tabs card-header-tabs"}
    (for [[title href] tabs]
      ^{:key href}
      [render-navigation-item title href current-hash-atom on-tab-click-fn])]])

(defn render-card [provider url title img text inputs on-submit-fn]
  [:div {:class "card-body"}
   [:div {:class "row"}
    [:div {:class "col-2"}
     [:a {:href url :title (if provider (str "Go to " provider) nil)}
      [:img {:src img, :class "card-img-top", :alt "..."}]]]

    [:div {:class "col-8"}
     [:h2 {:class "card-title"} title]
     [:p {:class "card-text"} text]

     [:form
      {:on-submit on-submit-fn}
      (for [[i input] (map-indexed vector inputs)]
        ^{:key i}
        [:div {:class "input-group mb-3 container"}
         input
         (when (= (- (count inputs) 1) i)
           [:button
            {:class "btn btn-outline-primary",
             :type "submit"}
            "Let's go"])])]]

    [:div {:class "col-2"}]]])

(defn input-field [name placeholder input-values-atom input-errors-atom on-change-fn]
  [:input
   {:type "text"
    :class ["form-control"
            (when (some #{name} @input-errors-atom)
              "validation-error")]
    :name name
    :placeholder placeholder
    :value (get @input-values-atom (keyword name))
    :on-change #(on-change-fn (.-target %) input-values-atom)}])
