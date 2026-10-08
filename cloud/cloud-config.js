/* ────────────────────────────────────────────────────────────────────────────
 * 云服务公开配置（publicConfig）
 *
 * 来源：workbuddy_cloud_service 的 activate 返回值。这三个值都会随页面下发到
 * 浏览器，属于**设计上允许公开**的内容：
 *   · publishableKey —— 只标识「这是哪个应用」，自身不带任何权限；
 *   · endpoint       —— 当前应用的发布域数据面地址，必须原样传给 SDK。
 * 服务端对请求做**精确 Origin 校验**，别处复制这份 key 也用不了。
 * 真正的凭据（环境 id、服务商密钥）只存在服务端，永远不会出现在这里。
 *
 * ⚠️ endpoint 只能来自这里，不要改用 window.location、环境变量或写死的测试域名
 *    —— 应用重新发布后域名会变，写死即失效。
 * ──────────────────────────────────────────────────────────────────────────── */
window.WC_CLOUD_CONFIG = {
  applicationId: 'wbapp_VPtKCSEAs0RVwIWRwLF3mX',
  resourceId: 'wbcs_SDbI9DWfGZwWbbuclS1Fqo',
  endpoint: 'https://xuhui-property-reports.app.workbuddy.host',
  publishableKey: 'wbpk_VPtKCSEAs0RVwIWRwLF3mX_Fq068wzA24qbRoolk2UiUPvE40GiieUk'
};
