import React, { useState } from 'react';
import { Layout, Menu, Button, Typography, Tooltip } from 'antd';
import {
  SafetyCertificateOutlined,
  DashboardOutlined,
  AppstoreOutlined,
  TeamOutlined,
  LogoutOutlined,
  SettingOutlined,
  PhoneOutlined,
} from '@ant-design/icons';
import DashboardPage from '@/pages/DashboardPage';
import AccountsPage from '@/pages/AccountsPage';
import GroupManage from '@/pages/GroupManage';
import SettingsPage from '@/pages/SettingsPage';
import SmsPage from '@/pages/SmsPage';
import './MainLayout.css';

const { Header, Sider, Content } = Layout;
const { Text } = Typography;

interface MainLayoutProps {
  onLogout: () => void;
}

const menuItems = [
  {
    key: 'dashboard',
    icon: <DashboardOutlined />,
    label: '仪表盘',
  },
  {
    key: 'accounts',
    icon: <AppstoreOutlined />,
    label: '账号管理',
  },
  {
    key: 'groups',
    icon: <TeamOutlined />,
    label: '分组管理',
  },
  {
    key: 'sms',
    icon: <PhoneOutlined />,
    label: '接码管理',
  },
  {
    key: 'settings',
    icon: <SettingOutlined />,
    label: '系统设置',
  },
];

const pageTitles: Record<string, string> = {
  dashboard: '仪表盘',
  accounts: '账号管理',
  groups: '分组管理',
  sms: '接码管理',
  settings: '系统设置',
};

const MainLayout: React.FC<MainLayoutProps> = ({ onLogout }) => {
  const [collapsed, setCollapsed] = useState(false);
  const [currentMenu, setCurrentMenu] = useState('dashboard');

  return (
    <Layout style={{ height: '100vh', overflow: 'hidden' }}>
      <Sider
        collapsible
        collapsed={collapsed}
        onCollapse={setCollapsed}
        theme="light"
        width={200}
        style={{
          borderRight: '1px solid #f0f0f0',
          boxShadow: '2px 0 8px rgba(0,0,0,0.02)',
          height: '100vh',
          overflow: 'auto',
        }}
      >
        <div className="logo-header">
          <div className="logo-dot">
            <SafetyCertificateOutlined style={{ fontSize: 16, color: '#fff' }} />
          </div>
          {!collapsed && (
            <Text strong style={{ fontSize: 15, whiteSpace: 'nowrap' }}>
              账号管理
            </Text>
          )}
        </div>

        <Menu
          mode="inline"
          selectedKeys={[currentMenu]}
          onClick={({ key }) => setCurrentMenu(key)}
          items={menuItems}
          style={{ border: 'none', marginTop: 8 }}
        />
      </Sider>

      <Layout style={{ height: '100vh', overflow: 'hidden' }}>
        <Header className="main-header">
          <div className="header-left">
            <Text strong style={{ fontSize: 16 }}>
              {pageTitles[currentMenu]}
            </Text>
          </div>
          <div className="header-right">
            <Tooltip title="退出登录">
              <Button
                type="text"
                icon={<LogoutOutlined />}
                onClick={onLogout}
                style={{ color: '#999' }}
              >
                退出
              </Button>
            </Tooltip>
          </div>
        </Header>

        <Content className="content-wrapper">
          <div className="site-layout-content">
            {currentMenu === 'dashboard' && <DashboardPage />}
            {currentMenu === 'accounts' && <AccountsPage />}
            {currentMenu === 'groups' && <GroupManage />}
            {currentMenu === 'sms' && <SmsPage />}
            {currentMenu === 'settings' && <SettingsPage />}
          </div>
        </Content>
      </Layout>
    </Layout>
  );
};

export default MainLayout;
