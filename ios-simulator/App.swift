import UIKit
import WebKit

final class WeatherViewController: UIViewController {
    override var preferredStatusBarStyle: UIStatusBarStyle { .lightContent }
}

final class AppDelegate: UIResponder, UIApplicationDelegate {
    var window: UIWindow?
    func application(_ application: UIApplication, didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]?) -> Bool {
        let controller = WeatherViewController()
        controller.view.backgroundColor = UIColor(red: 0.12, green: 0.20, blue: 0.31, alpha: 1)
        let web = WKWebView(frame: .zero)
        web.translatesAutoresizingMaskIntoConstraints = false
        web.isOpaque = false
        web.scrollView.contentInsetAdjustmentBehavior = .never
        web.backgroundColor = controller.view.backgroundColor
        controller.view.addSubview(web)
        NSLayoutConstraint.activate([
            web.topAnchor.constraint(equalTo: controller.view.topAnchor),
            web.bottomAnchor.constraint(equalTo: controller.view.bottomAnchor),
            web.leadingAnchor.constraint(equalTo: controller.view.leadingAnchor),
            web.trailingAnchor.constraint(equalTo: controller.view.trailingAnchor)
        ])
        let window = UIWindow(frame: UIScreen.main.bounds)
        window.rootViewController = controller
        window.makeKeyAndVisible()
        self.window = window
        let load = { web.load(URLRequest(url: URL(string: "http://127.0.0.1:5076/pilot")!)) }
        // Development-only handoff from the local pilot. Never embed a session in source.
        if let value = ProcessInfo.processInfo.environment["WEATHERAVATAR_SESSION"],
           let cookie = HTTPCookie(properties: [.domain: "127.0.0.1", .path: "/", .name: "weatheravatar_pilot", .value: value, .expires: Date(timeIntervalSinceNow: 86400 * 30), HTTPCookiePropertyKey("HttpOnly"): "TRUE"]) {
            web.configuration.websiteDataStore.httpCookieStore.setCookie(cookie) { _ = load() }
        } else { _ = load() }
        return true
    }
}
UIApplicationMain(CommandLine.argc, CommandLine.unsafeArgv, nil, NSStringFromClass(AppDelegate.self))
