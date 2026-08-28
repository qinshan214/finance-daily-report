/**
 * Cloudflare Workers 反向代理 - 火山引擎API代理
 * 功能：将GitHub Actions的请求代理到火山引擎API，解决国外服务器访问国内API慢的问题
 * 部署：Cloudflare Workers
 * 使用：将API地址替换为Worker地址即可
 */

export default {
  async fetch(request, env) {
    // 允许CORS
    const corsHeaders = {
      'Access-Control-Allow-Origin': '*',
      'Access-Control-Allow-Methods': 'GET, POST, PUT, DELETE, OPTIONS',
      'Access-Control-Allow-Headers': 'Content-Type, Authorization',
      'Access-Control-Max-Age': '86400',
    };

    // 处理OPTIONS预检请求
    if (request.method === 'OPTIONS') {
      return new Response(null, {
        status: 204,
        headers: corsHeaders,
      });
    }

    try {
      // 解析请求URL
      const url = new URL(request.url);
      
      // 目标API地址（火山引擎）
      const targetBase = 'https://ark.cn-beijing.volces.com';
      const targetUrl = targetBase + url.pathname + url.search;

      console.log(`代理请求: ${request.method} ${targetUrl}`);

      // 构建请求头
      const headers = new Headers(request.headers);
      // 移除可能导致问题的头
      headers.delete('host');
      headers.delete('cf-connecting-ip');
      headers.delete('cf-ipcountry');
      headers.delete('cf-ray');
      headers.delete('cf-visitor');
      headers.delete('x-forwarded-for');
      headers.delete('x-forwarded-proto');

      // 转发请求
      const response = await fetch(targetUrl, {
        method: request.method,
        headers: headers,
        body: request.body,
        // 禁用Cloudflare缓存，确保实时获取
        cf: {
          cacheTtl: 0,
          cacheEverything: false,
        },
      });

      console.log(`响应状态: ${response.status}`);

      // 构建响应头
      const responseHeaders = new Headers(response.headers);
      // 添加CORS头
      Object.entries(corsHeaders).forEach(([key, value]) => {
        responseHeaders.set(key, value);
      });

      // 返回响应
      return new Response(response.body, {
        status: response.status,
        statusText: response.statusText,
        headers: responseHeaders,
      });

    } catch (error) {
      console.error('代理错误:', error);
      
      // 返回错误响应
      return new Response(JSON.stringify({
        error: 'Proxy Error',
        message: error.message,
      }), {
        status: 502,
        headers: {
          'Content-Type': 'application/json',
          ...corsHeaders,
        },
      });
    }
  },
};
