// ==UserScript==
// @name         CatalogFlow Authorized Product Selector
// @namespace    https://github.com/qwq77777764/catalogflow
// @version      0.10.0
// @description  Send one operator-selected product URL to a local CatalogFlow queue.
// @match        https://www.alibaba.com/product-detail/*
// @match        https://www.cjdropshipping.com/product/*
// @match        https://cjdropshipping.com/product/*
// @grant        GM_xmlhttpRequest
// @connect      127.0.0.1
// @run-at       document-idle
// ==/UserScript==

(function () {
  "use strict";

  const PAGE_ORIGIN = location.origin;
  const SOURCE = PAGE_ORIGIN === "https://www.alibaba.com" ? "alibaba" : "cj";
  const PID = /^(?:[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}|\d{10,30})$/i;
  let sessionToken = "";
  let receiverBase = "";

  const alibabaPage = PAGE_ORIGIN === "https://www.alibaba.com" && location.pathname.startsWith("/product-detail/");
  const cjPage = ["https://www.cjdropshipping.com", "https://cjdropshipping.com"].includes(PAGE_ORIGIN)
    && location.pathname.startsWith("/product/");
  if (!alibabaPage && !cjPage) {
    return;
  }

  function selectedUrl() {
    const value = `${location.origin}${location.pathname}`;
    if (SOURCE === "alibaba") return value;
    const query = new URLSearchParams(location.search);
    for (const name of ["pid", "productId", "product_id"]) {
      const pid = query.get(name);
      if (pid && PID.test(pid)) return `${value}?${name}=${pid}`;
    }
    const matches = location.pathname.match(/(?<![a-z0-9])(?:[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}|\d{10,30})(?![a-z0-9])/gi) || [];
    return matches.length === 1 ? value : null;
  }

  if (!selectedUrl()) return;

  const button = document.createElement("button");
  button.type = "button";
  button.textContent = "Add to CatalogFlow";
  button.title = "Sends only this product URL and the current page title to your local receiver.";
  Object.assign(button.style, {
    position: "fixed",
    right: "20px",
    bottom: "22px",
    zIndex: "2147483647",
    border: "0",
    borderRadius: "999px",
    padding: "12px 18px",
    background: "#176b50",
    color: "#ffffff",
    font: "600 14px/1.2 system-ui, sans-serif",
    boxShadow: "0 8px 28px rgba(0, 0, 0, .22)",
    cursor: "pointer",
  });

  function promptForSession() {
    const code = window.prompt("Paste the pairing code from CatalogFlow / 粘贴 CatalogFlow 配对码");
    if (!code) return false;
    try {
      if (!/^CATALOGFLOW1:[A-Za-z0-9_-]{40,1200}$/.test(code.trim())) throw new Error();
      const encoded = code.trim().split(":")[1].replace(/-/g,"+").replace(/_/g,"/");
      const data = JSON.parse(atob(encoded + "=".repeat((4 - encoded.length % 4) % 4)));
      if (!data || Object.keys(data).sort().join(",") !== "endpoint,token") throw new Error();
      const match = /^http:\/\/127\.0\.0\.1:(\d{1,5})$/.exec(data.endpoint);
      if (!match || Number(match[1]) < 1 || Number(match[1]) > 65535
        || typeof data.token !== "string" || !/^[A-Za-z0-9_-]{32,128}$/.test(data.token)) throw new Error();
      receiverBase = data.endpoint;
      sessionToken = data.token;
      return true;
    } catch (_) {
      window.alert("Invalid pairing code. Copy it from CatalogFlow again. / 配对码无效，请重新复制。");
      return false;
    }
  }

  function setStatus(text, color) {
    button.textContent = text;
    button.style.background = color;
  }

  button.addEventListener("click", () => {
    const productUrl = selectedUrl();
    const pageTitle = document.title.trim().slice(0,240);
    if (!productUrl) { setStatus("Unsupported product URL", "#8f2f2a"); return; }
    const preview = [
      "Send exactly this selection to CatalogFlow on this computer?",
      "",
      `source: ${SOURCE}`,
      `product_url: ${productUrl}`,
      `page_title: ${pageTitle}`,
      "",
      "No cookies, HTML, images, prices, variants, or login data are sent.",
      "This only adds a link. Freeze the inbox in CatalogFlow before importing; AI does not start here.",
    ].join("\n");
    if (!window.confirm(preview)) return;
    if (!sessionToken && !promptForSession()) return;
    setStatus("Sending…", "#725112");
    const payload = JSON.stringify({
      version: 1,
      source: SOURCE,
      product_url: productUrl,
      page_title: pageTitle,
    });
    GM_xmlhttpRequest({
      method: "POST",
      url: `${receiverBase}/api/selections`,
      headers: {
        "Content-Type": "application/json",
        "X-CatalogFlow-Token": sessionToken,
        "X-CatalogFlow-Page-Origin": location.origin,
      },
      data: payload,
      timeout: 8000,
      anonymous: true,
      onload(response) {
        if (response.status === 200 || response.status === 201) {
          try {
            const result = JSON.parse(response.responseText);
            setStatus(result.created ? "Added ✓" : "Already queued", "#176b50");
          } catch (_error) {
            setStatus("Invalid receiver response", "#8f2f2a");
          }
        } else if (response.status === 403 || response.status === 409) {
          sessionToken = "";
          setStatus("Pair again", "#8f2f2a");
        } else {
          setStatus(`Rejected (${response.status})`, "#8f2f2a");
        }
      },
      onerror() {
        setStatus("Receiver offline", "#8f2f2a");
      },
      ontimeout() {
        setStatus("Receiver timeout", "#8f2f2a");
      },
    });
  });

  document.body.appendChild(button);
})();
