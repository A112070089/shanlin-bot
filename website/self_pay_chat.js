"use strict";

/* =========================================================
   山林診所｜自費加購模組 V1
   ---------------------------------------------------------
   功能：
   1. 開啟 / 關閉自費加購視窗
   2. 載入五大分類
   3. 載入分類下所有檢查項目
   4. 顯示檢查價格與說明
   5. 加入自費項目
   6. 同一套組避免重複計價
   7. 移除自費項目
   8. 顯示已選清單
   9. 自動計算總金額
   10. 確認後寫入 bookingData
   ========================================================= */

(() => {

  /* =====================================================
     API
     ===================================================== */

  const SELF_PAY_API_BASE =
    "http://127.0.0.1:8000/api/self_pay";


  /* =====================================================
     狀態
     ===================================================== */

  const selfPayState = {

    categories: [],

    currentCategoryId: null,

    selectedItems: []

  };

  window.selfPayState = selfPayState;


  /* =====================================================
     基本工具
     ===================================================== */

  function byId(id) {

    return document.getElementById(id);

  }


  function escapeHtml(value) {

    return String(value ?? "")

      .replaceAll("&", "&amp;")

      .replaceAll("<", "&lt;")

      .replaceAll(">", "&gt;")

      .replaceAll('"', "&quot;")

      .replaceAll("'", "&#039;");

  }


  function formatPrice(price) {

    if (
      price === null ||
      price === undefined ||
      price === ""
    ) {

      return "價格需確認";

    }

    const number = Number(price);

    if (!Number.isFinite(number)) {

      return "價格需確認";

    }

    return (
      "NT$" +
      number.toLocaleString("zh-TW")
    );

  }


  async function fetchJson(
    url,
    options = {}
  ) {

    const response =
      await fetch(
        url,
        options
      );

    let payload;

    try {

      payload =
        await response.json();

    } catch (error) {

      throw new Error(
        "伺服器回傳資料格式錯誤"
      );

    }

    if (!response.ok) {

      throw new Error(
        payload?.detail ||
        payload?.message ||
        `HTTP ${response.status}`
      );

    }

    if (
      payload?.status &&
      payload.status !== "success"
    ) {

      throw new Error(
        payload.message ||
        payload.detail ||
        "伺服器未回傳成功狀態"
      );

    }

    return payload;

  }


  /* =====================================================
     標題 / 內容
     ===================================================== */

  function setSelfPayHeading(
    title,
    subtitle,
    breadcrumb
  ) {

    const titleElement =
      byId("selfPayTitle");

    const subtitleElement =
      byId("selfPaySubtitle");

    const breadcrumbElement =
      byId("selfPayBreadcrumb");


    if (titleElement) {

      titleElement.textContent =
        title;

    }


    if (subtitleElement) {

      subtitleElement.textContent =
        subtitle;

    }


    if (breadcrumbElement) {

      breadcrumbElement.textContent =
        breadcrumb;

    }

  }


  function setSelfPayContent(html) {

    const content =
      byId("selfPayContent");

    if (!content) {

      console.error(
        "找不到 selfPayContent"
      );

      return;

    }

    content.innerHTML =
      html;

  }


  function showSelfPayLoading(
    message = "正在載入……"
  ) {

    setSelfPayContent(`

            <div class="self-pay-loading">

                ${escapeHtml(message)}

            </div>

        `);

  }


  function showSelfPayError(
    message
  ) {

    setSelfPayContent(`

            <div class="self-pay-error">

                <strong>
                    ⚠️ 無法載入資料
                </strong>

                <br><br>

                ${escapeHtml(message)}

                <br><br>

                請確認：

                <br>

                http://127.0.0.1:8000/docs

                <br><br>

                <button
                    type="button"
                    class="self-pay-back-btn"
                    onclick="window.showSelfPayCategories()">

                    重新載入

                </button>

            </div>

        `);

  }


  /* =====================================================
     開啟自費視窗
     ===================================================== */

  window.openSelfPayBrowser =
    function openSelfPayBrowser() {

      const modal =
        byId(
          "selfPayModal"
        );

      if (!modal) {

        alert(
          "找不到自費加購視窗。"
        );

        return;

      }


      modal.classList.add(
        "is-open"
      );

      modal.setAttribute(
        "aria-hidden",
        "false"
      );

      document.body
        .classList.add(
          "self-pay-modal-open"
        );


      window.showSelfPayCategories();

    };


  /* =====================================================
     關閉自費視窗
     ===================================================== */

  window.closeSelfPayBrowser =
    function closeSelfPayBrowser() {

      const modal =
        byId(
          "selfPayModal"
        );

      if (!modal) {

        return;

      }


      modal.classList.remove(
        "is-open"
      );

      modal.setAttribute(
        "aria-hidden",
        "true"
      );

      document.body
        .classList.remove(
          "self-pay-modal-open"
        );

    };


  /* =====================================================
     五大分類
     ===================================================== */

  window.showSelfPayCategories =
    async function showSelfPayCategories() {

      selfPayState.currentCategoryId =
        null;


      const backButton =
        byId(
          "selfPayBackButton"
        );


      if (backButton) {

        backButton.hidden =
          true;

      }


      setSelfPayHeading(

        "選擇自費檢查類型",

        "請先選擇您想了解的檢查大分類",

        "自費加購首頁"

      );


      showSelfPayLoading(
        "正在載入自費檢查分類……"
      );


      try {

        if (
          selfPayState
            .categories
            .length === 0
        ) {

          const payload =
            await fetchJson(

              `${SELF_PAY_API_BASE}/categories`

            );


          selfPayState.categories =
            Array.isArray(
              payload.categories
            )
              ? payload.categories
              : [];

        }


        renderSelfPayCategories(
          selfPayState.categories
        );


      } catch (error) {

        console.error(
          "載入自費分類失敗",
          error
        );


        showSelfPayError(
          error.message
        );

      }

    };


  /* =====================================================
     顯示分類卡片
     ===================================================== */

  function renderSelfPayCategories(
    categories
  ) {

    if (
      !Array.isArray(categories) ||
      categories.length === 0
    ) {

      setSelfPayContent(`

                <div class="self-pay-empty">

                    目前沒有可顯示的
                    自費檢查分類。

                </div>

            `);

      return;

    }


    const defaultIcons = {

      cardiovascular:
        "❤️",

      pulmonary:
        "🫁",

      hepatobiliary_gastrointestinal:
        "🫀",

      renal_urology:
        "🩺",

      other_value_added:
        "➕"

    };


    const cards =
      categories.map(
        category => {

          const id =
            escapeHtml(
              category.id
            );

          const name =
            escapeHtml(
              category.name ||
              "未命名分類"
            );

          const icon =
            escapeHtml(

              category.icon ||

              defaultIcons[
              category.id
              ] ||

              "🩺"

            );

          const count =
            Number(
              category.item_count ||
              0
            );


          return `

                        <button
                            type="button"
                            class="self-pay-category-card"
                            onclick="
                                window.showSelfPayCategoryItems(
                                    '${id}'
                                )
                            ">

                            <div>

                                <div
                                    class="self-pay-category-icon">

                                    ${icon}

                                </div>


                                <div
                                    class="self-pay-category-name">

                                    ${name}

                                </div>


                                <div
                                    class="self-pay-category-count">

                                    共 ${count} 項檢查

                                </div>

                            </div>


                            <div
                                class="self-pay-category-action">

                                查看檢查項目 →

                            </div>

                        </button>

                    `;

        }

      ).join("");


    setSelfPayContent(`

            <div
                class="self-pay-category-grid">

                ${cards}

            </div>

        `);

  }


  /* =====================================================
     點選大分類
     ===================================================== */

  window.showSelfPayCategoryItems =
    async function showSelfPayCategoryItems(
      categoryId
    ) {

      selfPayState.currentCategoryId =
        categoryId;


      const category =
        selfPayState.categories
          .find(
            item =>
              item.id ===
              categoryId
          );


      const categoryName =
        category?.name ||
        "自費檢查項目";


      const backButton =
        byId(
          "selfPayBackButton"
        );


      if (backButton) {

        backButton.hidden =
          false;

      }


      setSelfPayHeading(

        categoryName,

        "請選擇您想了解或加購的檢查項目",

        `自費加購首頁 ／ ${categoryName}`

      );


      showSelfPayLoading(

        `正在載入「${categoryName}」……`

      );


      try {

        const payload =
          await fetchJson(

            `${SELF_PAY_API_BASE}/category/` +
            encodeURIComponent(
              categoryId
            )

          );


        const items =
          Array.isArray(
            payload.items
          )
            ? payload.items
            : [];


        renderSelfPayItems(

          payload.category ||
          category,

          items

        );


      } catch (error) {

        console.error(
          "載入自費項目失敗",
          error
        );


        showSelfPayError(
          error.message
        );

      }

    };


  /* =====================================================
     顯示分類小項目
     ===================================================== */

  function renderSelfPayItems(
    category,
    items
  ) {

    const categoryName =
      escapeHtml(

        category?.name ||
        "自費檢查項目"

      );


    if (
      !Array.isArray(items) ||
      items.length === 0
    ) {

      setSelfPayContent(`

                <div
                    class="self-pay-empty">

                    此分類目前沒有
                    可顯示的檢查項目。

                </div>

            `);

      return;

    }


    const itemCards =
      items.map(
        item => {

          const itemId =
            escapeHtml(
              item.id
            );

          const itemName =
            escapeHtml(

              item.name ||
              "未命名檢查"

            );

          const itemCode =
            escapeHtml(
              item.code ||
              ""
            );

          const description =
            escapeHtml(

              item.clinical_reference ||

              "請洽診所了解檢查內容。"

            );

          const priceText =
            escapeHtml(

              item.price_text ||

              formatPrice(
                item.price
              )

            );


          const pricePending =

            item.price === null ||

            item.price ===
            undefined;


          const priceNote =
            escapeHtml(

              item.price_note ||
              ""

            );


          const alreadySelected =
            selfPayState
              .selectedItems
              .some(

                selected =>

                  selected
                    .sourceItemId ===
                  item.id

              );


          return `

                        <article
                            class="self-pay-item-card">


                            <div
                                class="self-pay-item-top">


                                <div>


                                    <div
                                        class="self-pay-item-name">

                                        ${itemName}

                                    </div>


                                    ${itemCode
              ? `

                                            <div
                                                class="self-pay-item-code">

                                                ${itemCode}

                                            </div>

                                            `
              : ""
            }


                                </div>


                                <div
                                    class="
                                    self-pay-item-price
                                    ${pricePending
              ? "price-pending"
              : ""
            }
                                    ">

                                    ${priceText}

                                </div>


                            </div>


                            <div
                                class="self-pay-item-description">

                                ${description}

                            </div>


                            ${priceNote
              ? `

                                    <div
                                        class="self-pay-item-note">

                                        ${priceNote}

                                    </div>

                                    `
              : ""
            }


                            <div
                                class="self-pay-item-actions">


                                <button
                                    type="button"
                                    class="self-pay-detail-btn"
                                    onclick="
                                        window.openSelfPayItemDetail(
                                            '${itemId}'
                                        )
                                    ">

                                    查看詳細內容

                                </button>


                                <button
                                    type="button"
                                    class="self-pay-add-btn"
                                    onclick="
                                        window.addSelfPayItem(
                                            '${itemId}'
                                        )
                                    "
                                    ${alreadySelected
              ? "disabled"
              : ""
            }>

                                    ${alreadySelected
              ? "已加入"
              : "加入"
            }

                                </button>


                            </div>


                        </article>

                    `;

        }

      ).join("");


    setSelfPayContent(`

            <div
                class="self-pay-items-heading">

                <h3>

                    ${categoryName}

                </h3>

                <p>

                    共 ${items.length} 項檢查。
                    可查看詳細內容，
                    或直接加入自費清單。

                </p>

            </div>


            <div
                class="self-pay-item-list">

                ${itemCards}

            </div>

        `);

  }


  /* =====================================================
     查看詳細內容
     ===================================================== */

  window.openSelfPayItemDetail =
    async function openSelfPayItemDetail(
      itemId
    ) {

      try {

        const payload =
          await fetchJson(

            `${SELF_PAY_API_BASE}/select`,

            {

              method:
                "POST",

              headers: {

                "Content-Type":
                  "application/json"

              },

              body:
                JSON.stringify({

                  item_id:
                    itemId

                })

            }

          );


        showSelfPayItemDialog(
          payload
        );


      } catch (error) {

        console.error(
          "取得自費項目詳細資料失敗",
          error
        );


        alert(

          "無法取得詳細資料：\n" +
          error.message

        );

      }

    };


  /* =====================================================
     詳細內容視窗
     ===================================================== */

  function showSelfPayItemDialog(
    payload
  ) {

    const oldDialog =
      byId(
        "selfPayDetailDialog"
      );


    if (oldDialog) {

      oldDialog.remove();

    }


    const item =
      payload.item ||
      {};


    const billable =
      payload.billable ||
      {};


    const itemName =
      escapeHtml(

        item.name ||

        billable.name ||

        "自費檢查"

      );


    const description =
      escapeHtml(

        item.clinical_reference ||

        "請洽診所了解檢查內容。"

      );


    const priceText =
      escapeHtml(

        formatPrice(
          billable.price
        )

      );


    const includedItems =
      Array.isArray(
        billable.included_items
      )
        ? billable.included_items
        : [];


    const includedHtml =
      includedItems.length

        ? `

                    <div
                        class="self-pay-item-note">

                        <strong>
                            套組包含：
                        </strong>

                        ${includedItems
          .map(
            escapeHtml
          )
          .join("、")
        }

                    </div>

                `

        : "";


    const dialog =
      document.createElement(
        "dialog"
      );


    dialog.id =
      "selfPayDetailDialog";


    dialog.className =
      "self-pay-detail-dialog";


    dialog.innerHTML = `

            <div
                class="self-pay-detail-body">


                <h3>

                    ${itemName}

                </h3>


                <div
                    class="self-pay-detail-price">

                    ${priceText}

                </div>


                <div
                    class="self-pay-detail-description">

                    ${description}

                </div>


                ${includedHtml}


                <div
                    class="self-pay-item-note">

                    ${escapeHtml(

      payload.medical_notice ||

      "是否適合加做，仍應由醫師或診所人員評估。"

    )
      }

                </div>


                <div
                    class="self-pay-item-actions">


                    <button
                        type="button"
                        class="self-pay-add-btn"
                        onclick="
                            window.addSelfPayItem(
                                '${escapeHtml(item.id)}'
                            );

                            document
                                .getElementById(
                                    'selfPayDetailDialog'
                                )
                                .close();
                        ">

                        加入此項目

                    </button>


                    <button
                        type="button"
                        class="self-pay-detail-close"
                        onclick="
                            document
                                .getElementById(
                                    'selfPayDetailDialog'
                                )
                                .close();
                        ">

                        關閉

                    </button>


                </div>


            </div>

        `;


    document.body
      .appendChild(
        dialog
      );


    dialog.addEventListener(

      "close",

      () =>
        dialog.remove(),

      {
        once:
          true
      }

    );


    dialog.showModal();

  }


  /* =====================================================
     加入自費項目
     ===================================================== */

  window.addSelfPayItem =
    async function addSelfPayItem(
      itemId
    ) {

      try {

        const payload =
          await fetchJson(

            `${SELF_PAY_API_BASE}/select`,

            {

              method:
                "POST",

              headers: {

                "Content-Type":
                  "application/json"

              },

              body:
                JSON.stringify({

                  item_id:
                    itemId

                })

            }

          );


        const item =
          payload.item ||
          {};


        const billable =
          payload.billable ||
          {};


        const uniqueKey =
          billable.key ||

          `item:${itemId}`;


        const existing =
          selfPayState
            .selectedItems
            .find(

              selected =>

                selected.key ===
                uniqueKey

            );


        if (existing) {

          if (
            existing.type ===
            "package"
          ) {

            alert(

              `「${item.name}」所屬套組已加入，不會重複計價。`

            );

          } else {

            alert(
              "此項目已經加入。"
            );

          }


          return;

        }


        selfPayState
          .selectedItems
          .push({

            key:
              uniqueKey,

            sourceItemId:
              itemId,

            name:

              billable.name ||

              item.name ||

              "未命名項目",

            selectedItemName:

              billable
                .selected_item_name ||

              item.name ||

              "",

            price:

              billable.price ??
              null,

            type:

              billable.type ||
              "item",

            includedItems:

              Array.isArray(
                billable
                  .included_items
              )

                ? billable
                  .included_items

                : [],

            category:

              billable.category ||

              item.category ||

              ""

          });


        updateSelfPaySummary();


        alert(

          `已加入：${billable.name ||
          item.name ||
          "自費檢查項目"
          }`

        );


        if (
          selfPayState
            .currentCategoryId
        ) {

          await window
            .showSelfPayCategoryItems(

              selfPayState
                .currentCategoryId

            );

        }


      } catch (error) {

        console.error(
          "加入自費項目失敗",
          error
        );


        alert(

          "加入失敗：\n" +
          error.message

        );

      }

    };


  /* =====================================================
     計算總金額
     ===================================================== */

  function getSelfPayTotal() {

    return selfPayState
      .selectedItems
      .reduce(

        (
          total,
          item
        ) => {

          const price =
            Number(
              item.price
            );


          return Number
            .isFinite(
              price
            )

            ? total +
            price

            : total;

        },

        0

      );

  }


  /* =====================================================
     更新右下角摘要
     ===================================================== */

  function updateSelfPaySummary() {

    let box =
      byId(
        "selfPaySummary"
      );


    if (!box) {

      box =
        document.createElement(
          "div"
        );


      box.id =
        "selfPaySummary";


      box.className =
        "self-pay-summary";


      document.body
        .appendChild(
          box
        );

    }


    if (
      selfPayState
        .selectedItems
        .length === 0
    ) {

      box.style.display =
        "none";

      return;

    }


    box.innerHTML = `

            <div
                class="self-pay-summary-info">

                <strong>

                    已選
                    ${selfPayState
        .selectedItems
        .length
      }
                    項

                </strong>

                <span>

                    合計
                    ${formatPrice(
        getSelfPayTotal()
      )
      }

                </span>

            </div>


            <button
                type="button"
                class="self-pay-summary-button"
                onclick="
                    window.openSelfPayCart()
                ">

                查看清單

            </button>

        `;


    box.style.display =
      "flex";


    box.style.visibility =
      "visible";


    box.style.opacity =
      "1";

  }


  window.updateSelectedSummary =
    updateSelfPaySummary;


  /* =====================================================
     查看清單
     ===================================================== */

  window.openSelfPayCart =
    function openSelfPayCart() {

      const oldDialog =
        byId(
          "selfPayCartDialog"
        );


      if (oldDialog) {

        oldDialog.remove();

      }


      const dialog =
        document.createElement(
          "dialog"
        );


      dialog.id =
        "selfPayCartDialog";


      dialog.className =

        "self-pay-detail-dialog " +
        "self-pay-cart-dialog";


      document.body
        .appendChild(
          dialog
        );


      renderSelfPayCart(
        dialog
      );


      dialog.addEventListener(

        "close",

        () =>
          dialog.remove(),

        {
          once:
            true
        }

      );


      dialog.showModal();

    };


  /* =====================================================
     顯示購物車
     ===================================================== */

  function renderSelfPayCart(
    dialog
  ) {

    if (
      selfPayState
        .selectedItems
        .length === 0
    ) {

      dialog.innerHTML = `

                <div
                    class="self-pay-detail-body">


                    <h3>

                        自費加購清單

                    </h3>


                    <div
                        class="self-pay-empty">

                        目前尚未選擇
                        任何項目。

                    </div>


                    <button
                        type="button"
                        class="self-pay-detail-close"
                        onclick="
                            document
                                .getElementById(
                                    'selfPayCartDialog'
                                )
                                .close()
                        ">

                        關閉

                    </button>


                </div>

            `;


      return;

    }


    const rows =
      selfPayState
        .selectedItems
        .map(

          item => {


            const included =
              item
                .includedItems
                .length

                ? `

                                <div
                                    class="self-pay-cart-included">

                                    套組包含：

                                    ${item
                  .includedItems
                  .map(
                    escapeHtml
                  )
                  .join("、")
                }

                                </div>

                                `

                : "";


            return `

                            <div
                                class="self-pay-cart-row">


                                <div
                                    class="self-pay-cart-main">


                                    <strong>

                                        ${escapeHtml(
              item.name
            )
              }

                                    </strong>


                                    ${item
                .selectedItemName &&

                item
                  .selectedItemName !==
                item.name

                ? `

                                            <div
                                                class="self-pay-cart-selected-source">

                                                因選擇「${escapeHtml(
                  item.selectedItemName
                )
                }」加入

                                            </div>

                                            `

                : ""
              }


                                    ${included}


                                </div>


                                <div
                                    class="self-pay-cart-price">

                                    ${escapeHtml(
                formatPrice(
                  item.price
                )
              )
              }

                                </div>


                                <button
                                    type="button"
                                    class="self-pay-cart-remove"
                                    onclick="
                                        window.removeSelfPayItem(
                                            '${escapeHtml(item.key)}'
                                        )
                                    ">

                                    移除

                                </button>


                            </div>

                        `;

          }

        ).join("");


    dialog.innerHTML = `

            <div
                class="self-pay-detail-body">


                <h3>

                    自費加購清單

                </h3>


                <div
                    class="self-pay-cart-list">

                    ${rows}

                </div>


                <div
                    class="self-pay-cart-total">

                    <span>

                        合計

                    </span>


                    <strong>

                        ${escapeHtml(
      formatPrice(
        getSelfPayTotal()
      )
    )
      }

                    </strong>

                </div>


                <div
                    class="self-pay-item-note">

                    價格需確認的項目
                    不計入目前合計；
                    最終金額以診所確認為準。

                </div>


                <div
                    class="self-pay-item-actions">


                    <button
                        type="button"
                        class="self-pay-add-btn"
                        onclick="
                            window.confirmSelfPaySelection()
                        ">

                        確認加購

                    </button>


                    <button
                        type="button"
                        class="self-pay-detail-close"
                        onclick="
                            document
                                .getElementById(
                                    'selfPayCartDialog'
                                )
                                .close()
                        ">

                        繼續選擇

                    </button>


                </div>


            </div>

        `;

  }


  /* =====================================================
     移除項目
     ===================================================== */

  window.removeSelfPayItem =
    function removeSelfPayItem(
      key
    ) {

      selfPayState.selectedItems =

        selfPayState
          .selectedItems
          .filter(

            item =>

              item.key !==
              key

          );


      updateSelfPaySummary();


      const cartDialog =
        byId(
          "selfPayCartDialog"
        );


      if (
        cartDialog &&
        cartDialog.open
      ) {

        renderSelfPayCart(
          cartDialog
        );

      }


      if (
        selfPayState
          .currentCategoryId
      ) {

        window
          .showSelfPayCategoryItems(

            selfPayState
              .currentCategoryId

          );

      }

    };


  /* =====================================================
     確認加購
     ===================================================== */

  window.confirmSelfPaySelection =
    function confirmSelfPaySelection() {

      if (
        selfPayState
          .selectedItems
          .length === 0
      ) {

        alert(
          "目前尚未選擇任何項目。"
        );

        return;

      }


      /*
       * bookingData 在原老人健檢
       * index_dev.html 中已存在。
       */

      if (
        typeof bookingData !==
        "undefined"
      ) {

        bookingData.selfPayItems =

          selfPayState
            .selectedItems
            .map(

              item => ({

                key:
                  item.key,

                name:
                  item.name,

                selected_item_name:
                  item.selectedItemName,

                price:
                  item.price,

                type:
                  item.type,

                category:
                  item.category,

                included_items:
                  item.includedItems

              })

            );


        bookingData.selfPayTotal =
          getSelfPayTotal();

      }


      const dialog =
        byId(
          "selfPayCartDialog"
        );


      if (
        dialog &&
        dialog.open
      ) {

        dialog.close();

      }


      window
        .closeSelfPayBrowser();


      alert(

        `已確認 ${selfPayState
          .selectedItems
          .length
        } 項自費加購。\n\n` +

        `目前合計：${formatPrice(
          getSelfPayTotal()
        )
        }`

      );


      console.log(

        "自費項目：",

        selfPayState
          .selectedItems

      );


      console.log(

        "自費總金額：",

        getSelfPayTotal()

      );

    };


  /* =====================================================
     ESC 關閉
     ===================================================== */

  document.addEventListener(

    "keydown",

    event => {

      if (
        event.key !==
        "Escape"
      ) {

        return;

      }


      const cartDialog =
        byId(
          "selfPayCartDialog"
        );


      if (
        cartDialog &&
        cartDialog.open
      ) {

        cartDialog.close();

        return;

      }


      const detailDialog =
        byId(
          "selfPayDetailDialog"
        );


      if (
        detailDialog &&
        detailDialog.open
      ) {

        detailDialog.close();

        return;

      }


      const modal =
        byId(
          "selfPayModal"
        );


      if (
        modal &&
        modal.classList
          .contains(
            "is-open"
          )
      ) {

        window
          .closeSelfPayBrowser();

      }

    }

  );


  /* =====================================================
     網頁載入
     ===================================================== */

  window.addEventListener(

    "load",

    () => {

      updateSelfPaySummary();

    }

  );

})();