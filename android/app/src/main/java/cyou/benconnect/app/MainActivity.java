package cyou.benconnect.app;

import android.annotation.SuppressLint;
import android.app.Activity;
import android.app.DownloadManager;
import android.content.ActivityNotFoundException;
import android.content.Intent;
import android.graphics.Color;
import android.net.Uri;
import android.os.Bundle;
import android.os.Environment;
import android.view.View;
import android.view.WindowInsets;
import android.webkit.CookieManager;
import android.webkit.ValueCallback;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceError;
import android.webkit.WebResourceRequest;
import android.webkit.WebResourceResponse;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.PopupMenu;
import android.widget.ProgressBar;
import android.widget.TextView;
import android.widget.Toast;

public final class MainActivity extends Activity {
    private static final String HOME = "https://benconnect.cyou/";
    private static final int FILE_REQUEST = 10;
    private WebView web;
    private ProgressBar progress;
    private LinearLayout error;
    private ValueCallback<Uri[]> fileCallback;
    private String failedUrl = HOME;
    private boolean loadFailed;

    static boolean isInternal(Uri uri) {
        return "https".equalsIgnoreCase(uri.getScheme())
                && "benconnect.cyou".equalsIgnoreCase(uri.getHost())
                && (uri.getPort() == -1 || uri.getPort() == 443)
                && uri.getUserInfo() == null;
    }

    @SuppressLint("SetJavaScriptEnabled")
    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setBackgroundColor(Color.WHITE);
        // Android 15 draws edge-to-edge; keep controls clear of system bars and keyboard.
        if (android.os.Build.VERSION.SDK_INT >= 30) root.setOnApplyWindowInsetsListener((v, insets) -> {
            android.graphics.Insets bars = insets.getInsets(WindowInsets.Type.systemBars()
                    | WindowInsets.Type.displayCutout() | WindowInsets.Type.ime());
            v.setPadding(bars.left, bars.top, bars.right, bars.bottom);
            return insets;
        });
        // WindowInsets.Type is only available starting with API 30.
        if (android.os.Build.VERSION.SDK_INT < 30) {
            root.setOnApplyWindowInsetsListener((v, insets) -> {
                v.setPadding(insets.getSystemWindowInsetLeft(), insets.getSystemWindowInsetTop(),
                        insets.getSystemWindowInsetRight(), insets.getSystemWindowInsetBottom());
                return insets;
            });
        }
        LinearLayout toolbar = new LinearLayout(this);
        toolbar.setGravity(android.view.Gravity.CENTER_VERTICAL);
        Button back = new Button(this);
        back.setText("‹");
        back.setContentDescription("Zurück");
        back.setOnClickListener(v -> navigateBack());
        toolbar.addView(back, new LinearLayout.LayoutParams(dp(54), dp(48)));
        TextView title = new TextView(this);
        title.setText("BenConnect");
        title.setTextSize(19);
        title.setTextColor(Color.rgb(35, 48, 95));
        toolbar.addView(title, new LinearLayout.LayoutParams(0, dp(48), 1));
        title.setGravity(android.view.Gravity.CENTER_VERTICAL);
        Button menu = new Button(this);
        menu.setText("⋮");
        menu.setContentDescription("App-Menü");
        menu.setOnClickListener(this::showMenu);
        toolbar.addView(menu, new LinearLayout.LayoutParams(dp(54), dp(48)));
        root.addView(toolbar);
        progress = new ProgressBar(this, null, android.R.attr.progressBarStyleHorizontal);
        root.addView(progress, new LinearLayout.LayoutParams(-1, dp(3)));
        error = new LinearLayout(this);
        error.setOrientation(LinearLayout.VERTICAL);
        error.setPadding(dp(24), dp(32), dp(24), dp(24));
        TextView message = new TextView(this);
        message.setText("BenConnect konnte nicht geladen werden. Prüfe deine Internetverbindung und versuche es erneut.");
        message.setTextSize(18);
        error.addView(message);
        Button retry = new Button(this);
        retry.setText("Erneut versuchen");
        retry.setOnClickListener(v -> web.loadUrl(failedUrl));
        error.addView(retry);
        error.setVisibility(View.GONE);
        root.addView(error, new LinearLayout.LayoutParams(-1, -2));
        web = new WebView(this);
        root.addView(web, new LinearLayout.LayoutParams(-1, 0, 1));
        setContentView(root);
        WebSettings settings = web.getSettings();
        settings.setJavaScriptEnabled(true);
        settings.setDomStorageEnabled(true);
        settings.setAllowFileAccess(false);
        settings.setAllowContentAccess(false);
        settings.setMixedContentMode(WebSettings.MIXED_CONTENT_NEVER_ALLOW);
        settings.setUserAgentString(settings.getUserAgentString() + " BenConnectAndroid/" + BuildConfig.VERSION_NAME);
        CookieManager.getInstance().setAcceptCookie(true);
        CookieManager.getInstance().setAcceptThirdPartyCookies(web, false);
        web.setWebViewClient(new WebViewClient() {
            @Override public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
                if (isInternal(request.getUrl())) return false;
                if (request.isForMainFrame()) openExternal(request.getUrl());
                return true;
            }
            @Override public void onPageStarted(WebView view, String url, android.graphics.Bitmap icon) {
                loadFailed = false;
                error.setVisibility(View.GONE);
                web.setVisibility(View.VISIBLE);
                progress.setVisibility(View.VISIBLE);
            }
            @Override public void onPageFinished(WebView view, String url) {
                progress.setVisibility(View.GONE);
                CookieManager.getInstance().flush();
            }
            @Override public void onReceivedError(WebView view, WebResourceRequest request, WebResourceError failure) {
                if (request.isForMainFrame()) showError(request.getUrl().toString());
            }
            @Override public void onReceivedSslError(WebView view, android.webkit.SslErrorHandler handler,
                    android.net.http.SslError sslError) {
                handler.cancel();
                showError(sslError.getUrl());
            }
            @Override public void onReceivedHttpError(WebView view, WebResourceRequest request, WebResourceResponse response) {
                if (request.isForMainFrame() && response.getStatusCode() >= 500) showError(request.getUrl().toString());
            }
        });
        web.setWebChromeClient(new WebChromeClient() {
            @Override public void onProgressChanged(WebView view, int value) { progress.setProgress(value); }
            @Override public boolean onShowFileChooser(WebView view, ValueCallback<Uri[]> callback, FileChooserParams params) {
                if (fileCallback != null) fileCallback.onReceiveValue(null);
                fileCallback = callback;
                try {
                    startActivityForResult(params.createIntent(), FILE_REQUEST);
                } catch (ActivityNotFoundException e) {
                    fileCallback.onReceiveValue(null);
                    fileCallback = null;
                    toast("Keine Dateiauswahl verfügbar.");
                }
                return true;
            }
        });
        web.setDownloadListener((url, agent, disposition, mime, length) -> download(url, disposition, mime));
        if (state == null || web.restoreState(state) == null) web.loadUrl(HOME);
        if (android.os.Build.VERSION.SDK_INT >= 33) {
            getOnBackInvokedDispatcher().registerOnBackInvokedCallback(
                    android.window.OnBackInvokedDispatcher.PRIORITY_DEFAULT, this::navigateBack);
        }
    }

    private int dp(int value) { return Math.round(value * getResources().getDisplayMetrics().density); }
    private void toast(String text) { Toast.makeText(this, text, Toast.LENGTH_LONG).show(); }
    private void navigateBack() { if (web.canGoBack()) web.goBack(); else finish(); }
    @Override public void onBackPressed() { navigateBack(); }
    private void showError(String url) {
        loadFailed = true;
        failedUrl = isInternal(Uri.parse(url)) ? url : HOME;
        progress.setVisibility(View.GONE);
        web.setVisibility(View.GONE);
        error.setVisibility(View.VISIBLE);
    }
    private void showMenu(View anchor) {
        PopupMenu menu = new PopupMenu(this, anchor);
        menu.getMenu().add(0, 1, 0, "Neu laden");
        menu.getMenu().add(0, 2, 1, "Startseite");
        menu.getMenu().add(0, 3, 2, "App herunterladen / aktualisieren");
        menu.getMenu().add(0, 4, 3, "Version " + BuildConfig.VERSION_NAME).setEnabled(false);
        menu.setOnMenuItemClickListener(item -> {
            if (item.getItemId() == 1) { if (loadFailed) web.loadUrl(failedUrl); else web.reload(); }
            if (item.getItemId() == 2) web.loadUrl(HOME);
            if (item.getItemId() == 3) openExternal(Uri.parse(HOME + "android.html"));
            return true;
        });
        menu.show();
    }
    private void openExternal(Uri uri) {
        String scheme = uri.getScheme();
        if (!("https".equals(scheme) || "http".equals(scheme) || "mailto".equals(scheme)
                || "tel".equals(scheme) || "geo".equals(scheme))) {
            toast("Dieser Link wird nicht unterstützt.");
            return;
        }
        try { startActivity(new Intent(Intent.ACTION_VIEW, uri).addCategory(Intent.CATEGORY_BROWSABLE)); }
        catch (ActivityNotFoundException e) { toast("Keine passende App für diesen Link gefunden."); }
    }
    private void download(String url, String disposition, String mime) {
        // The website creates the account export as a temporary blob. Download its
        // authenticated source directly, avoiding a privileged JavaScript bridge.
        if (url.startsWith("blob:" + HOME) && web.getUrl() != null
                && isInternal(Uri.parse(web.getUrl()))
                && "/settings.html".equals(Uri.parse(web.getUrl()).getPath())) {
            url = HOME + "api/account/export";
            disposition = "attachment; filename=meine-daten.json";
            mime = "application/json";
        }
        Uri uri = Uri.parse(url);
        if (!isInternal(uri)) { openExternal(uri); return; }
        try {
            String name = android.webkit.URLUtil.guessFileName(url, disposition, mime);
            name = name.replaceAll("[^a-zA-Z0-9._-]", "_");
            DownloadManager.Request request = new DownloadManager.Request(uri);
            String cookies = CookieManager.getInstance().getCookie(url);
            if (cookies != null) request.addRequestHeader("Cookie", cookies);
            request.addRequestHeader("User-Agent", web.getSettings().getUserAgentString());
            request.setMimeType(mime);
            request.setTitle(name);
            request.setNotificationVisibility(DownloadManager.Request.VISIBILITY_VISIBLE_NOTIFY_COMPLETED);
            request.setDestinationInExternalPublicDir(Environment.DIRECTORY_DOWNLOADS, name);
            ((DownloadManager) getSystemService(DOWNLOAD_SERVICE)).enqueue(request);
            toast("Download gestartet. Du findest die Datei unter Downloads.");
        } catch (RuntimeException e) { toast("Download konnte nicht gestartet werden."); }
    }
    @Override protected void onActivityResult(int request, int result, Intent data) {
        super.onActivityResult(request, result, data);
        if (request == FILE_REQUEST && fileCallback != null) {
            Uri[] selection = WebChromeClient.FileChooserParams.parseResult(result, data);
            if (selection != null) {
                for (Uri uri : selection) {
                    if (!"content".equals(uri.getScheme()) || getPackageName().equals(uri.getAuthority())) {
                        selection = null;
                        break;
                    }
                }
            }
            fileCallback.onReceiveValue(selection);
            fileCallback = null;
        }
    }
    @Override protected void onSaveInstanceState(Bundle state) { super.onSaveInstanceState(state); web.saveState(state); }
    @Override protected void onPause() { CookieManager.getInstance().flush(); web.onPause(); super.onPause(); }
    @Override protected void onResume() { super.onResume(); if (web != null) web.onResume(); }
    @Override protected void onDestroy() {
        if (fileCallback != null) fileCallback.onReceiveValue(null);
        web.destroy();
        super.onDestroy();
    }
}
