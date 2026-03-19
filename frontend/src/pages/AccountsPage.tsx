import React, { useState, useEffect, useRef, useCallback } from 'react';
import {
  Button,
  Input,
  Select,
  Tag,
  Modal,
  Table,
  Pagination,
  Typography,
  Tooltip,
  Flex,
  App,
  Space,
} from 'antd';
import type { ColumnsType } from 'antd/es/table';
import {
  PlusOutlined,
  EditOutlined,
  DeleteOutlined,
  CopyOutlined,
  SearchOutlined,
  CrownOutlined,
  UserOutlined,
  TeamOutlined,
  EyeOutlined,
  EyeInvisibleOutlined,
  ImportOutlined,
  KeyOutlined,
  LockOutlined,
  ClockCircleOutlined,
  LoginOutlined,
  PoweroffOutlined,
  LoadingOutlined,
} from '@ant-design/icons';
import {
  getAccounts,
  deleteAccount,
  getGroups,
  getTags,
  getTOTP,
  importAccounts,
  getBrowserProfiles,
  createBrowserProfile,
  launchBrowser,
  stopBrowser,
} from '@/api';
import type { Account } from '@/types';
import AccountModal from '@/components/AccountModal';
import { maskEmail } from '@/utils/mask';

const { Text } = Typography;

/** 标签颜色池 */
const TAG_COLORS = [
  'blue', 'purple', 'cyan', 'geekblue', 'magenta', 'volcano', 'gold', 'green',
];
const tagColorMap = new Map<string, string>();
const getTagColor = (tag: string) => {
  if (!tagColorMap.has(tag)) {
    tagColorMap.set(tag, TAG_COLORS[tagColorMap.size % TAG_COLORS.length]);
  }
  return tagColorMap.get(tag)!;
};

const AccountsPage: React.FC = () => {
  const { message: msg } = App.useApp();
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [loading, setLoading] = useState(false);
  const [modalVisible, setModalVisible] = useState(false);
  const [editingAccount, setEditingAccount] = useState<Account | null>(null);
  const [searchText, setSearchText] = useState('');
  const [groupFilter, setGroupFilter] = useState<string | undefined>();
  const [tagFilter, setTagFilter] = useState<string | undefined>();
  const [groups, setGroups] = useState<string[]>([]);
  const [tags, setTags] = useState<string[]>([]);
  const [masked, setMasked] = useState(false);
  const [ownerOnly, setOwnerOnly] = useState(false);
  const [currentPage, setCurrentPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);
  const [total, setTotal] = useState(0);

  // 导入
  const [importVisible, setImportVisible] = useState(false);
  const [importText, setImportText] = useState('');
  const [importLoading, setImportLoading] = useState(false);

  // 浏览器状态
  const [browserRunning, setBrowserRunning] = useState<Set<number>>(new Set());
  const [browserLoading, setBrowserLoading] = useState<Set<number>>(new Set());
  const [profileMap, setProfileMap] = useState<Record<number, number>>({});

  useEffect(() => {
    loadAccounts();
    loadFilters();
  }, [searchText, groupFilter, tagFilter, currentPage, pageSize, ownerOnly]);

  useEffect(() => {
    loadBrowserStatus();
  }, []);

  const loadAccounts = async () => {
    setLoading(true);
    try {
      const { data } = await getAccounts(searchText, groupFilter, tagFilter, currentPage, pageSize, ownerOnly);
      setAccounts(data.accounts);
      setTotal(data.total);
    } catch {
      msg.error('加载账号失败');
    } finally {
      setLoading(false);
    }
  };

  const loadFilters = async () => {
    try {
      const [groupsRes, tagsRes] = await Promise.all([getGroups(), getTags()]);
      setGroups(groupsRes.data.groups);
      setTags(tagsRes.data.tags);
    } catch { /* silent */ }
  };

  const loadBrowserStatus = async () => {
    try {
      const { data } = await getBrowserProfiles();
      const map: Record<number, number> = {};
      const running = new Set<number>();
      for (const p of data.profiles) {
        if (p.account_id) {
          map[p.account_id] = p.id;
          if (p.status === 'running') running.add(p.account_id);
        }
      }
      setProfileMap(map);
      setBrowserRunning(running);
    } catch { /* silent */ }
  };

  const WS_URL = 'ws://localhost:8000/api/v1/ws/automation';

  const handleLaunchAndLogin = async (record: Account) => {
    const accountId = record.id;
    setBrowserLoading((prev) => new Set(prev).add(accountId));
    try {
      let profileId = profileMap[accountId];
      if (!profileId) {
        const res = await createBrowserProfile({
          name: record.email || `Profile-${accountId}`,
          account_id: accountId,
          proxy_type: '', proxy_host: '', proxy_port: null,
          proxy_username: '', proxy_password: '', user_agent: '',
          os_type: 'macos', timezone: '', language: 'en-US',
          screen_width: 1920, screen_height: 1080,
          webrtc_disabled: true, notes: '',
        });
        profileId = res.data.id;
        setProfileMap((prev) => ({ ...prev, [accountId]: profileId }));
      }
      await launchBrowser(profileId);
      setBrowserRunning((prev) => new Set(prev).add(accountId));
      msg.success('浏览器已启动，开始自动登录...');

      // 通过 WebSocket 触发自动登录（不显示日志）
      const token = localStorage.getItem('token') || '';
      const ws = new WebSocket(`${WS_URL}?token=${token}`);
      ws.onopen = () => {
        ws.send(JSON.stringify({ action: 'login', account_id: accountId }));
      };
      ws.onmessage = (e) => {
        try {
          const data = JSON.parse(e.data);
          if (data.type === 'result') {
            if (data.success) msg.success(data.message || '登录成功');
            else msg.warning(data.message || '登录失败');
            ws.close();
          } else if (data.type === 'error') {
            msg.error(data.message || '登录异常');
            ws.close();
          }
        } catch { /* ignore */ }
      };
      ws.onerror = () => { msg.error('WebSocket 连接失败'); };
    } catch (err: any) {
      msg.error(err.response?.data?.detail || '启动失败');
    } finally {
      setBrowserLoading((prev) => { const next = new Set(prev); next.delete(accountId); return next; });
    }
  };

  const handleStopBrowser = async (accountId: number) => {
    const profileId = profileMap[accountId];
    if (!profileId) return;
    setBrowserLoading((prev) => new Set(prev).add(accountId));
    try {
      await stopBrowser(profileId);
      setBrowserRunning((prev) => { const next = new Set(prev); next.delete(accountId); return next; });
      msg.success('浏览器已停止');
    } catch (err: any) {
      msg.error(err.response?.data?.detail || '停止失败');
    } finally {
      setBrowserLoading((prev) => { const next = new Set(prev); next.delete(accountId); return next; });
    }
  };

  const handleAdd = () => { setEditingAccount(null); setModalVisible(true); };
  const handleEdit = (record: Account) => { setEditingAccount(record); setModalVisible(true); };
  const handleDelete = (id: number) => {
    Modal.confirm({
      title: '确认删除', content: '确定要删除这个账号吗？',
      okText: '删除', okType: 'danger', cancelText: '取消',
      onOk: async () => {
        try { await deleteAccount(id); msg.success('已删除'); loadAccounts(); loadFilters(); }
        catch { msg.error('删除失败'); }
      },
    });
  };

  const copyToClipboard = (text: string, label: string) => {
    navigator.clipboard.writeText(text).then(() => msg.success(`${label}已复制`));
  };

  const copyFullAccount = (record: Account) => {
    const parts = [record.email, record.password, record.recovery_email || '', record.totp_secret || ''];
    navigator.clipboard.writeText(parts.join('----')).then(() => msg.success('账号信息已复制'));
  };

  const copyTOTPCode = async (accountId: number) => {
    try {
      const { data } = await getTOTP(accountId);
      await navigator.clipboard.writeText(data.code);
      msg.success(`2FA 验证码已复制: ${data.code}`);
    } catch (error: any) {
      msg.error(error.response?.data?.detail || '获取验证码失败');
    }
  };

  const handleImport = async () => {
    if (!importText.trim()) { msg.warning('请输入要导入的账号信息'); return; }
    setImportLoading(true);
    try {
      const res = await importAccounts(importText);
      const data = res.data;
      if (data.success > 0) msg.success(data.message);
      else if (data.skipped > 0) msg.warning(data.message);
      else msg.error(data.message);
      if (data.success > 0) {
        setImportVisible(false); setImportText(''); loadAccounts(); loadFilters();
      }
    } catch (err: any) {
      msg.error(err.response?.data?.detail || '导入失败');
    } finally { setImportLoading(false); }
  };

  const columns: ColumnsType<Account> = [
    {
      title: '邮箱',
      dataIndex: 'email',
      key: 'email',
      ellipsis: true,
      render: (email: string, record) => (
        <Flex align="center" gap={6}>
          <Text
            style={{ cursor: 'pointer', fontSize: 13 }}
            onClick={() => copyToClipboard(email, '邮箱')}
          >
            {masked ? maskEmail(email) : email}
          </Text>
          {record.subscription_status === 'ultra' && (
            <Tag color="purple" style={{ margin: 0, fontSize: 10, lineHeight: '16px', padding: '0 4px', cursor: 'default' }}>
              Ultra
            </Tag>
          )}
          {record.subscription_status === 'ultra' && record.subscription_expiry && (
            <Tag color="default" style={{ margin: 0, fontSize: 10, lineHeight: '16px', padding: '0 4px', cursor: 'default' }}>
              重置于 {record.subscription_expiry}
            </Tag>
          )}
          {record.is_family_owner && (
            <CrownOutlined style={{ color: '#faad14', fontSize: 12 }} />
          )}
          {record.is_family_pending && (
            <ClockCircleOutlined style={{ color: '#fa8c16', fontSize: 12 }} />
          )}
        </Flex>
      ),
    },
    {
      title: '分组',
      key: 'group',
      width: 140,
      render: (_, record) => (
        <Flex gap={4} align="center" wrap>
          {record.group_name && (
            <Tag style={{ margin: 0, fontSize: 11 }}>{record.group_name}</Tag>
          )}
          {record.family_group_id && (record.family_member_count ?? 0) > 0 && (
            <Tag color="default" style={{ margin: 0, fontSize: 11 }}>
              <TeamOutlined style={{ marginRight: 2 }} />{Math.max((record.family_member_count ?? 0) - 1, 0)}/5
            </Tag>
          )}
        </Flex>
      ),
    },
    {
      title: '角色',
      key: 'role',
      width: 80,
      render: (_, record) => {
        if (!record.family_group_id) return <Text type="secondary" style={{ fontSize: 12 }}>-</Text>;
        if (record.is_family_pending) {
          return <Tag color="orange" style={{ margin: 0, fontSize: 11 }}><ClockCircleOutlined style={{ marginRight: 2 }} />待接受</Tag>;
        }
        if (record.is_family_owner) {
          return <Tag color="gold" style={{ margin: 0, fontSize: 11 }}><CrownOutlined style={{ marginRight: 2 }} />管理</Tag>;
        }
        return <Tag color="blue" style={{ margin: 0, fontSize: 11 }}><UserOutlined style={{ marginRight: 2 }} />成员</Tag>;
      },
    },
    {
      title: '地区',
      dataIndex: 'country_cn',
      key: 'country',
      width: 80,
      render: (_: string | null, record: Account) => {
        const cn = record.country_cn;
        const en = record.country;
        if (!cn && !en) return null;
        return <Tooltip title={en}><Text style={{ fontSize: 12 }}>{cn || en}</Text></Tooltip>;
      },
    },
    {
      title: '标签',
      dataIndex: 'tags',
      key: 'tags',
      width: 140,
      render: (tags: string | null) =>
        tags ? (
          <Flex gap={4} wrap>
            {tags.split(',').map((t, i) => (
              <Tag key={i} color={getTagColor(t.trim())} style={{ margin: 0, fontSize: 11 }}>{t.trim()}</Tag>
            ))}
          </Flex>
        ) : null,
    },
    {
      title: '备注',
      dataIndex: 'notes',
      key: 'notes',
      width: 160,
      ellipsis: true,
      render: (notes: string | null) => notes ? <Text type="secondary" style={{ fontSize: 12 }}>{notes}</Text> : null,
    },
    {
      title: '创建时间',
      dataIndex: 'created_at',
      key: 'created_at',
      width: 100,
      render: (val: string | null) => {
        if (!val) return null;
        const d = new Date(val);
        return <Text type="secondary" style={{ fontSize: 12 }}>{d.toLocaleDateString('zh-CN', { month: '2-digit', day: '2-digit' })} {d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })}</Text>;
      },
    },
    {
      title: '操作',
      key: 'actions',
      width: 210,
      fixed: 'right',
      render: (_, record) => {
        const isRunning = browserRunning.has(record.id);
        const isBrowserLoading = browserLoading.has(record.id);
        return (
        <Space size={0}>
          {/* 启动/停止浏览器 */}
          <Tooltip title={isBrowserLoading ? '处理中' : isRunning ? '关闭浏览器' : '启动并登录'}>
            <Button
              type="text" size="small"
              disabled={isBrowserLoading}
              icon={isBrowserLoading ? <LoadingOutlined style={{ color: '#1677ff' }} />
                : isRunning ? <PoweroffOutlined style={{ color: '#ff4d4f' }} />
                : <LoginOutlined style={{ color: '#4285f4' }} />}
              onClick={() => isRunning ? handleStopBrowser(record.id) : handleLaunchAndLogin(record)}
            />
          </Tooltip>
          {/* 复制密码 */}
          {record.password && (
            <Tooltip title="复制密码">
              <Button
                type="text" size="small"
                icon={<LockOutlined style={{ color: '#faad14' }} />}
                onClick={() => copyToClipboard(record.password, '密码')}
              />
            </Tooltip>
          )}
          {/* 复制 2FA */}
          {record.totp_secret && (
            <Tooltip title="复制 2FA 验证码">
              <Button
                type="text" size="small"
                icon={<KeyOutlined style={{ color: '#52c41a' }} />}
                onClick={() => copyTOTPCode(record.id)}
              />
            </Tooltip>
          )}
          {/* 复制全部 */}
          <Tooltip title="复制全部信息">
            <Button
              type="text" size="small"
              icon={<CopyOutlined style={{ color: '#1677ff' }} />}
              onClick={() => copyFullAccount(record)}
            />
          </Tooltip>
          {/* 编辑 */}
          <Tooltip title="编辑">
            <Button
              type="text" size="small"
              icon={<EditOutlined style={{ color: '#8c8c8c' }} />}
              onClick={() => handleEdit(record)}
            />
          </Tooltip>
          {/* 删除 */}
          <Tooltip title="删除">
            <Button
              type="text" size="small"
              icon={<DeleteOutlined style={{ color: '#ff4d4f' }} />}
              onClick={() => handleDelete(record.id)}
            />
          </Tooltip>
        </Space>
      );},
    },
  ];

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      {/* 工具栏 */}
      <Flex justify="space-between" align="center" style={{ marginBottom: 16, flexShrink: 0 }} wrap gap={12}>
        <Flex gap={8} wrap>
          <Input
            placeholder="搜索邮箱或备注"
            prefix={<SearchOutlined style={{ color: '#bfbfbf' }} />}
            style={{ width: 220 }}
            onChange={(e) => { setSearchText(e.target.value); setCurrentPage(1); }}
            allowClear
          />
          <Select
            placeholder="分组" style={{ width: 140 }}
            onChange={(v) => { setGroupFilter(v); setCurrentPage(1); }}
            allowClear options={groups.map((g) => ({ label: g, value: g }))}
          />
          <Select
            placeholder="标签" style={{ width: 140 }}
            onChange={(v) => { setTagFilter(v); setCurrentPage(1); }}
            allowClear options={tags.map((t) => ({ label: t, value: t }))}
          />
        </Flex>
        <Flex gap={8} align="center">
          <Tooltip title="添加账号">
            <Button type="text" icon={<PlusOutlined />} onClick={handleAdd} />
          </Tooltip>
          <Tooltip title="批量导入">
            <Button type="text" icon={<ImportOutlined />} onClick={() => setImportVisible(true)} />
          </Tooltip>
          <Tooltip title={ownerOnly ? '显示全部账号' : '仅显示创建者'}>
            <Button
              type={ownerOnly ? 'primary' : 'text'}
              icon={<CrownOutlined />}
              onClick={() => { setOwnerOnly((v) => !v); setCurrentPage(1); }}
              style={ownerOnly ? { boxShadow: 'none' } : {}}
            />
          </Tooltip>
          <Tooltip title={masked ? '显示邮箱' : '隐藏邮箱'}>
            <Button type="text" icon={masked ? <EyeInvisibleOutlined /> : <EyeOutlined />} onClick={() => setMasked((v) => !v)} />
          </Tooltip>
        </Flex>
      </Flex>

      {/* 表格 */}
      <div style={{ flex: 1, minHeight: 0, overflow: 'hidden' }}>
        <Table<Account>
          columns={columns}
          dataSource={accounts}
          rowKey="id"
          loading={loading}
          size="small"
          scroll={{ x: 800, y: 'calc(100vh - 260px)' }}
          pagination={false}
        />
      </div>

      {/* 分页 - 固定底部居中 */}
      <Flex justify="center" align="center" style={{ padding: '12px 0', flexShrink: 0 }}>
        <Pagination
          current={currentPage}
          pageSize={pageSize}
          total={total}
          showSizeChanger
          pageSizeOptions={['10', '20', '50', '100']}
          showTotal={(t) => `共 ${t} 个账号`}
          onChange={(p, ps) => { setCurrentPage(p); setPageSize(ps); }}
          size="small"
        />
      </Flex>

      {/* 导入弹窗 */}
      <Modal
        title="批量导入账号"
        open={importVisible}
        onCancel={() => { setImportVisible(false); setImportText(''); }}
        onOk={handleImport}
        okText="导入"
        cancelText="取消"
        confirmLoading={importLoading}
        width={600}
      >
        <div style={{ marginBottom: 12 }}>
          <Text type="secondary">
            每行一个账号，字段用 <Text code>----</Text> 或 <Text code>|</Text> 分隔，智能识别字段类型：
          </Text>
          <br />
          <Text type="secondary" style={{ fontSize: 12 }}>
            含 @ → 辅助邮箱 | http(s)开头 → 链接(存备注) | 其他 → 2FA密钥
          </Text>
        </div>
        <Input.TextArea
          rows={8}
          placeholder={`支持多种格式，例如：\nemail----密码----辅助邮箱----2FA密钥----短信链接\nemail|密码|辅助邮箱|2FA密钥|国家\nemail----密码----辅助邮箱`}
          value={importText}
          onChange={(e) => setImportText(e.target.value)}
          style={{ fontFamily: 'monospace', fontSize: 12 }}
        />
        {importText.trim() && (
          <div style={{ marginTop: 8 }}>
            <Text type="secondary">
              共 {importText.trim().split('\n').filter((l) => l.trim()).length} 条记录
            </Text>
          </div>
        )}
      </Modal>

      <AccountModal
        visible={modalVisible}
        account={editingAccount}
        onClose={() => setModalVisible(false)}
        onSuccess={() => { loadAccounts(); loadFilters(); }}
      />
    </div>
  );
};

export default AccountsPage;
