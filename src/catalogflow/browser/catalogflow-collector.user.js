// ==UserScript==
// @name         CatalogFlow Authorized Product Selector
// @namespace    https://github.com/qwq77777764/catalogflow
// @version      0.4.0
// @description  Send one operator-selected product URL to a local CatalogFlow queue.
// @match        https://www.alibaba.com/product-detail/*
// @grant        GM_xmlhttpRequest
// @connect      127.0.0.1
// @run-at       document-idle
// ==/UserScript==

(function () {
  "use strict";

  const SOURCE = "alibaba";
  const PAGE_ORIGIN = "https://www.alibaba.com";
  const DEFAULT_RECEIVER = "http://127.0.0.1:8766";
  let sessionToken = "";
  let receiverBase = DEFAULT_RECEIVER;

  if (location.origin !== PAGE_ORIGIN || !location.pathname.startsWith("/product-detail/")) {
    return;
  }

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
    const base = window.prompt("CatalogFlow receiver URL", receiverBase);
    if (!base) return false;
    const match = /^http:\/\/127\.0\.0\.1:(\d{1,5})$/.exec(base.trim());
    if (!match || Number(match[1]) < 1 || Number(match[1]) > 65535) {
      window.alert("Use the exact 127.0.0.1 receiver URL printed by catalogflow collect.");
      return false;
    }
    const token = window.prompt("CatalogFlow one-time session token");
    if (!token || token.length < 32 || token.length > 128) return false;
    receiverBase = base.trim();
    sessionToken = token.trim();
    return true;
  }

  function setStatus(text, color) {
    button.textContent = text;
    button.style.background = color;
  }

  button.addEventListener("click", () => {
    const productUrl = `${location.origin}${location.pathname}`;
    const preview = [
      "Send exactly this selection to CatalogFlow on this computer?",
      "",
      `source: ${SOURCE}`,
      `product_url: ${productUrl}`,
      `page_title: ${document.title}`,
      "",
      "No cookies, HTML, images, prices, variants, or login data are sent.",
    ].join("\n");
    if (!window.confirm(preview)) return;
    if (!sessionToken && !promptForSession()) return;
    setStatus("Sending…", "#725112");
    const payload = JSON.stringify({
      version: 1,
      source: SOURCE,
      product_url: productUrl,
      page_title: document.title,
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
        } else if (response.status === 403) {
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
