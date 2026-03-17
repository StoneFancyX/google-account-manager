/** Ant Design 主题配置 */
import type { ThemeConfig } from 'antd';

const theme: ThemeConfig = {
  token: {
    // 品牌色 - Google 蓝
    colorPrimary: '#4285f4',
    colorInfo: '#4285f4',
    // 圆角
    borderRadius: 8,
    borderRadiusLG: 12,
    // 字体
    fontFamily:
      "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif",
    // 阴影
    boxShadow: '0 2px 8px rgba(0, 0, 0, 0.06)',
    boxShadowSecondary: '0 4px 16px rgba(0, 0, 0, 0.08)',
  },
  components: {
    Layout: {
      headerBg: '#ffffff',
      siderBg: '#ffffff',
      bodyBg: '#f5f7fa',
    },
    Menu: {
      itemBorderRadius: 8,
      itemMarginInline: 8,
      itemHeight: 44,
    },
    Button: {
      borderRadius: 8,
      controlHeight: 36,
    },
    Card: {
      borderRadiusLG: 12,
    },
    Table: {
      borderRadiusLG: 12,
      headerBg: '#fafbfc',
    },
    Input: {
      borderRadius: 8,
    },
    Select: {
      borderRadius: 8,
    },
    Modal: {
      borderRadiusLG: 16,
    },
  },
};

export default theme;
