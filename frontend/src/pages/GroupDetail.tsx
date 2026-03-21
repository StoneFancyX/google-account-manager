import React, { useState, useEffect, useCallback } from 'react';
import {
  Button,
  Card,
  Tag,
  Modal,
  message,
  Typography,
  Tooltip,
  Flex,
  Dropdown,
  Empty,
  Spin,
  Divider,
  Space,
  Input,
  Select,
  App,
} from 'antd';
import {
  ArrowLeftOutlined,
  CrownOutlined,
  UserOutlined,
  GoogleOutlined,
  TeamOutlined,
  MoreOutlined,
  CopyOutlined,
  EditOutlined,
  DeleteOutlined,
  LoginOutlined,
  PoweroffOutlined,
  LoadingOutlined,
  SyncOutlined,
  UserAddOutlined,
  UserDeleteOutlined,
  CheckCircleOutlined,
  LogoutOutlined,
  SwapOutlined,
  EyeOutlined,
  EyeInvisibleOutlined,
  ClockCircleOutlined,
  SafetyCertificateOutlined,
  DownloadOutlined,
  FileTextOutlined,
  LinkOutlined,
  PhoneOutlined,
} from '@ant-design/icons';
import {
  getGroup,
  getTOTP,
  launchBrowser,
  stopBrowser,
  getBrowserProfiles,
  createBrowserProfile,
  addAccountToGroup,
  removeAccountFromGroup,
  clearBrowserData,
  discoverFamily,
  getAccounts,
  getOAuthCredential,
  downloadOAuthCredential,
} from '@/api';
import type { Account, Group } from '@/types';
import { maskEmail } from '@/utils/mask';

const { Text, Title } = Typography;

const WS_URL = 'ws://localhost:8000/api/v1/ws/automation';

/** WebSocket 步骤消息 */
interface StepMsg {
  type: 'step' | 'result' | 'error';
  step?: number;
  name?: string;
  status?: string;
  message?: string;
  success?: boolean;
  duration_ms?: number;
}

/** 每个账号独立的操作状态 */
interface AccountOpState {
  runningOpKey: string | null;
  steps: StepMsg[];
  resultMsg: string;
  resultSuccess: boolean | null;
}

/** 操作定义 */
interface OpDef {
  key: string;
  label: string;
  icon: React.ReactNode;
  color: string;
  needBrowser: boolean;
  fields?: { name: string; placeholder: string }[];
  danger?: boolean;
  role?: 'any' | 'owner' | 'member' | 'no-group';
}

const OPERATIONS: OpDef[] = [
  { key: 'family-discover', label: '同步', icon: <SyncOutlined />, color: '#1677ff', needBrowser: false, role: 'owner' },
  { key: 'family-create', label: '建组', icon: <TeamOutlined />, color: '#722ed1', needBrowser: true, role: 'no-group' },
  { key: 'family-invite', label: '邀请', icon: <UserAddOutlined />, color: '#13c2c2', needBrowser: true, fields: [{ name: 'invite_email', placeholder: '被邀请人邮箱（多个用逗号或换行分隔）' }], role: 'owner' },
  { key: 'family-accept', label: '接受', icon: <CheckCircleOutlined />, color: '#52c41a', needBrowser: true, role: 'no-group' },
  { key: 'family-remove', label: '移除', icon: <UserDeleteOutlined />, color: '#ff4d4f', needBrowser: true, fields: [{ name: 'member_email', placeholder: '要移除的成员邮箱（多个用逗号或换行分隔）' }], danger: true, role: 'owner' },
  { key: 'family-leave', label: '退组', icon: <LogoutOutlined />, color: '#fa8c16', needBrowser: true, danger: true, role: 'member' },
  { key: 'replace', label: '替换', icon: <SwapOutlined />, color: '#722ed1', needBrowser: true, fields: [{ name: 'old_email', placeholder: '旧成员邮箱 (将被移除)' }, { name: 'new_email', placeholder: '新成员邮箱 (将被邀请)' }], role: 'owner' },
];

/** 获取该账号可见的操作列表 */
const getVisibleOps = (account: Account) => {
  const hasGroup = !!account.family_group_id;
  const isOwner = !!account.is_family_owner;
  const isMember = hasGroup && !isOwner;
  const isFull = (account.family_member_count ?? 0) >= 6; // 含管理员共 6 人

  return OPERATIONS.filter((op) => {
    if (!op.role || op.role === 'any') return true;
    if (op.role === 'owner') {
      if (!isOwner) return false;
      if (isFull && op.key === 'family-invite') return false;
      return true;
    }
    if (op.role === 'member') return isMember;
    if (op.role === 'no-group') return !hasGroup;
    return true;
  });
};

interface GroupDetailProps {
  groupId: number;
  onBack: () => void;
}

const GroupDetail: React.FC<GroupDetailProps> = ({ groupId, onBack }) => {
  const { message: msg } = App.useApp();
  const [group, setGroup] = useState<Group | null>(null);
  const [loading, setLoading] = useState(false);
  const [masked, setMasked] = useState(false);

  // 浏览器状态
  const [browserRunning, setBrowserRunning] = useState<Set<number>>(new Set());
  const [browserLoading, setBrowserLoading] = useState<Set<number>>(new Set());
  const [profileMap, setProfileMap] = useState<Record<number, number>>({});

  // 每个账号独立的操作状态
  const [opStates, setOpStates] = useState<Record<number, AccountOpState>>({});

  // 输入字段弹窗
  const [activeOp, setActiveOp] = useState<OpDef | null>(null);
  const [activeAccountId, setActiveAccountId] = useState<number | null>(null);
  const [formValues, setFormValues] = useState<Record<string, string>>({});
  // 多选邮箱 (邀请/移除)
  const [selectedEmails, setSelectedEmails] = useState<string[]>([]);
  // 替换操作: 旧成员选择 + 新成员输入
  const [replaceOldEmail, setReplaceOldEmail] = useState<string>('');
  const [replaceNewEmail, setReplaceNewEmail] = useState<string>('');

  // 选中的账号 (右侧日志面板)
  const [selectedAccountId, setSelectedAccountId] = useState<number | null>(null);

  // 添加成员
  const [addMemberVisible, setAddMemberVisible] = useState(false);
  const [allAccounts, setAllAccounts] = useState<Account[]>([]);

  useEffect(() => {
    loadGroup();
    loadBrowserStatus();
  }, [groupId]);

  const loadGroup = async () => {
    setLoading(true);
    try {
      const { data } = await getGroup(groupId);
      setGroup(data);
    } catch {
      msg.error('加载分组详情失败');
    } finally {
      setLoading(false);
    }
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

  const handleLaunchBrowser = async (accountId: number) => {
    setSelectedAccountId(accountId);
    setBrowserLoading((prev) => new Set(prev).add(accountId));
    try {
      let profileId = profileMap[accountId];
      if (!profileId) {
        const account = (group?.accounts || []).find((a) => a.id === accountId);
        const res = await createBrowserProfile({
          name: account?.email || `Profile-${accountId}`,
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
      setBrowserLoading((prev) => { const next = new Set(prev); next.delete(accountId); return next; });
      executeViaWs(accountId, 'login', {}, 'login');
      return;
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

  const handleClearBrowserData = (accountId: number) => {
    const profileId = profileMap[accountId];
    if (!profileId) {
      msg.error('未找到浏览器配置');
      return;
    }
    Modal.confirm({
      title: '确认清除浏览器数据',
      content: '此操作将删除该账号的所有浏览器数据（cookies、缓存等），但保留配置。确定继续？',
      okText: '确认清除',
      cancelText: '取消',
      okButtonProps: { danger: true },
      onOk: async () => {
        try {
          await clearBrowserData(profileId);
          msg.success('浏览器数据已清除');
        } catch (err: any) {
          msg.error(err.response?.data?.detail || '清除失败');
        }
      },
    });
  };

  // --- 自动化操作 via WebSocket ---
  const executeViaWs = useCallback(
    (accountId: number, action: string, extra: Record<string, string> = {}, opKey?: string) => {
      const trackKey = opKey || action;
      const token = localStorage.getItem('token') || '';
      const ws = new WebSocket(`${WS_URL}?token=${token}`);

      // 自动选中该账号的日志面板
      setSelectedAccountId(accountId);

      setOpStates(prev => ({
        ...prev,
        [accountId]: { runningOpKey: trackKey, steps: [], resultMsg: '', resultSuccess: null }
      }));

      ws.onopen = () => {
        ws.send(JSON.stringify({ action, account_id: accountId, ...extra }));
      };

      ws.onmessage = (e) => {
        try {
          const data: StepMsg = JSON.parse(e.data);
          if (data.type === 'step') {
            setOpStates(prev => {
              const s = prev[accountId];
              if (!s) return prev;
              const newSteps = (() => {
                if (data.status === 'running') return [...s.steps, data];
                const updated = [...s.steps];
                let idx = -1;
                for (let j = updated.length - 1; j >= 0; j--) {
                  if (updated[j].step === data.step) { idx = j; break; }
                }
                if (idx >= 0) updated[idx] = data;
                else updated.push(data);
                return updated;
              })();
              return { ...prev, [accountId]: { ...s, steps: newSteps } };
            });
          } else if (data.type === 'result') {
            setOpStates(prev => ({
              ...prev,
              [accountId]: {
                ...prev[accountId],
                runningOpKey: null,
                resultMsg: data.message || '',
                resultSuccess: data.success ?? false,
              }
            }));
            if (data.success) {
              msg.success(data.message || '操作成功');
              loadGroup();
            } else {
              msg.warning(data.message || '操作失败');
            }
            ws.close();
          } else if (data.type === 'error') {
            setOpStates(prev => ({
              ...prev,
              [accountId]: {
                ...prev[accountId],
                runningOpKey: null,
                resultMsg: data.message || '操作异常',
                resultSuccess: false,
              }
            }));
            msg.error(data.message || '操作异常');
            ws.close();
          }
        } catch { /* ignore */ }
      };

      ws.onerror = () => {
        setOpStates(prev => ({
          ...prev,
          [accountId]: {
            ...prev[accountId],
            runningOpKey: null,
            resultMsg: 'WebSocket 连接失败',
            resultSuccess: false,
          }
        }));
        msg.error('WebSocket 连接失败');
      };
    },
    [msg, groupId],
  );

  const handleOpClick = (accountId: number, op: OpDef) => {
    if (op.key === 'family-discover') {
      handleDiscover(accountId);
      return;
    }
    if (op.needBrowser && !browserRunning.has(accountId)) {
      msg.warning('请先启动浏览器');
      return;
    }
    const actionKey = op.key === 'family-delete' ? 'family-leave' : op.key;
    if (!op.fields) {
      executeViaWs(accountId, actionKey, {}, op.key);
      return;
    }
    setFormValues({});
    setSelectedEmails([]);
    setReplaceOldEmail('');
    setReplaceNewEmail('');
    setActiveOp(op);
    setActiveAccountId(accountId);
  };

  const handleDiscover = async (accountId: number) => {
    setOpStates(prev => ({
      ...prev,
      [accountId]: { runningOpKey: 'family-discover', steps: [], resultMsg: '', resultSuccess: null }
    }));
    try {
      const { data } = await discoverFamily(accountId);
      if (data.success) {
        msg.success(data.message || '同步成功');
        loadGroup();
      } else if (data.cookies_expired) {
        msg.warning(data.message || 'Cookies 已过期，请重新登录');
      } else {
        msg.warning(data.message || '同步失败');
      }
    } catch (err: any) {
      msg.error(err.response?.data?.detail || '同步请求失败');
    } finally {
      setOpStates(prev => ({
        ...prev,
        [accountId]: { ...prev[accountId], runningOpKey: null }
      }));
    }
  };

  const handleFieldModalOk = () => {
    if (!activeOp || !activeAccountId) return;

    if (activeOp.key === 'family-invite') {
      if (selectedEmails.length === 0) {
        msg.warning('请输入至少一个邮箱');
        return;
      }
      executeViaWs(activeAccountId, 'family-batch-invite', { invite_emails: selectedEmails.join(',') }, 'family-invite');
    } else if (activeOp.key === 'family-remove') {
      if (selectedEmails.length === 0) {
        msg.warning('请选择至少一个成员');
        return;
      }
      executeViaWs(activeAccountId, 'family-batch-remove', { member_emails: selectedEmails.join(',') }, 'family-remove');
    } else if (activeOp.key === 'replace') {
      if (!replaceOldEmail) {
        msg.warning('请选择要移除的成员');
        return;
      }
      if (!replaceNewEmail.trim()) {
        msg.warning('请输入新成员邮箱');
        return;
      }
      executeViaWs(activeAccountId, 'family-replace', { old_email: replaceOldEmail, new_email: replaceNewEmail.trim() }, 'replace');
    } else {
      for (const f of activeOp.fields || []) {
        if (!formValues[f.name]?.trim()) {
          msg.warning(`请输入${f.placeholder}`);
          return;
        }
      }
      const extra: Record<string, string> = {};
      for (const f of activeOp.fields || []) extra[f.name] = formValues[f.name].trim();
      executeViaWs(activeAccountId, activeOp.key, extra, activeOp.key);
    }
    setActiveOp(null);
    setActiveAccountId(null);
  };

  /** 获取当前操作账号所在家庭组的成员列表（排除操作者自身） */
  const getMemberOptions = () => {
    if (!activeAccountId || !group) return [];
    const activeAccount = (group.accounts || []).find((a) => a.id === activeAccountId);
    if (!activeAccount) return [];
    // 获取同一家庭组内的其他成员
    return (group.accounts || [])
      .filter((a) => a.id !== activeAccountId && a.family_group_id === activeAccount.family_group_id)
      .map((a) => ({ label: a.email, value: a.email }));
  };

  /** 处理邀请 Select 粘贴/输入: 支持逗号、换行、空格分隔多邮箱 */
  const handleInviteSearch = (value: string) => {
    // 检测是否粘贴了多邮箱（含逗号、换行、分号）
    if (/[,;\n\r]/.test(value)) {
      const emails = value
        .split(/[,;\n\r\s]+/)
        .map((e) => e.trim())
        .filter((e) => e && e.includes('@'));
      if (emails.length > 0) {
        setSelectedEmails((prev) => [...new Set([...prev, ...emails])]);
      }
    }
  };

  const copyToClipboard = (text: string, label: string) => {
    navigator.clipboard.writeText(text).then(() => msg.success(`${label}已复制`));
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

  const handleOAuth = (accountId: number) => {
    if (!browserRunning.has(accountId)) {
      msg.warning('请先启动浏览器');
      return;
    }
    executeViaWs(accountId, 'oauth', {}, 'oauth');
  };

  const handleCopyOAuthJson = async (accountId: number) => {
    try {
      const { data } = await getOAuthCredential(accountId);
      await navigator.clipboard.writeText(JSON.stringify(data, null, 2));
      msg.success('OAuth JSON 已复制到剪贴板');
    } catch (error: any) {
      msg.error(error.response?.data?.detail || '获取 OAuth 凭证失败');
    }
  };

  const handleDownloadOAuth = async (accountId: number) => {
    try {
      const { blob, filename } = await downloadOAuthCredential(accountId);
      const a = document.createElement('a');
      a.href = URL.createObjectURL(blob);
      a.download = filename;
      a.click();
      URL.revokeObjectURL(a.href);
      msg.success('下载成功');
    } catch (error: any) {
      msg.error(error.response?.data?.detail || '下载失败');
    }
  };

  // 以下代码用于兼容，但不再被右上角按钮触发
  const handleAddMember = async () => {
    try {
      const { data } = await getAccounts('', undefined, undefined, 1, 999);
      setAllAccounts(data.accounts.filter((a: Account) => !a.family_group_id));
      setAddMemberVisible(true);
    } catch {
      msg.error('加载账号列表失败');
    }
  };

  const handleAddAccountToGroup = async (accountId: number) => {
    try {
      await addAccountToGroup(groupId, accountId);
      msg.success('账号已添加到分组');
      setAddMemberVisible(false);
      loadGroup();
    } catch (err: any) {
      msg.error(err.response?.data?.detail || '添加失败');
    }
  };

  const handleRemoveFromGroup = async (accountId: number) => {
    try {
      await removeAccountFromGroup(accountId);
      msg.success('账号已从分组移除');
      loadGroup();
    } catch {
      msg.error('移除失败');
    }
  };

  if (loading && !group) {
    return (
      <Flex justify="center" align="center" style={{ height: '100%' }}>
        <Spin size="large" />
      </Flex>
    );
  }

  if (!group) {
    return (
      <Flex vertical align="center" justify="center" style={{ height: '100%' }}>
        <Empty description="分组不存在" />
        <Button type="link" onClick={onBack}>返回列表</Button>
      </Flex>
    );
  }

  const mainAccount = (group.accounts || []).find((a) => a.id === group.main_account_id);
  // 子号 + 待接受 合并，子号在前，待接受在后
  const memberAccounts = (group.accounts || [])
    .filter((a) => a.id !== group.main_account_id)
    .sort((a, b) => (a.is_family_pending ? 1 : 0) - (b.is_family_pending ? 1 : 0));
  /** 渲染账号卡片 (主号/子号通用) - 不含日志区 */
  const renderAccountCard = (record: Account, isMain: boolean) => {
    const isPending = !!record.is_family_pending;
    const isRunning = browserRunning.has(record.id);
    const isBrowserLoading = browserLoading.has(record.id);
    const visibleOps = isPending ? [] : getVisibleOps(record);
    const opState = opStates[record.id];
    const isThisAccountRunning = !!opState?.runningOpKey;
    const runningOpKey = opState?.runningOpKey || null;
    const memberCount = record.family_member_count ?? 0;
    const isSelected = selectedAccountId === record.id;

    return (
      <div
        key={record.id}
        style={{ marginBottom: 6, cursor: 'pointer' }}
        onClick={() => setSelectedAccountId(record.id)}
      >
        <Card
          size="small"
          className="hover-card"
          style={{
            borderRadius: 8,
            border: isSelected
              ? '2px solid #1677ff'
              : isPending
                ? '1px dashed #ffd591'
                : isMain
                  ? '1px solid #ffd666'
                  : isRunning
                    ? '1px solid #91caff'
                    : '1px solid #f0f0f0',
            transition: 'all 0.2s',
            opacity: isPending ? 0.8 : 1,
          }}
          styles={{ body: { padding: '8px 10px 6px' } }}
        >
          {/* 顶部: 邮箱 + 操作 */}
          <Flex justify="space-between" align="flex-start" style={{ marginBottom: 4 }}>
            <Flex
              align="center" gap={6}
              style={{ flex: 1, minWidth: 0 }}
            >
              <GoogleOutlined style={{ color: '#4285f4', fontSize: 14, flexShrink: 0 }} />
              <Tooltip title="点击复制邮箱">
                <Text strong ellipsis style={{ fontSize: 12, maxWidth: '100%', cursor: 'pointer' }}
                  onClick={(e) => { e.stopPropagation(); copyToClipboard(record.email, '邮箱'); }}>
                  {masked ? maskEmail(record.email) : record.email}
                </Text>
              </Tooltip>
            </Flex>
            <Dropdown
              menu={{
                items: [
                  ...(isMain ? [] : [{
                    key: 'remove-from-group',
                    icon: <UserDeleteOutlined />,
                    label: '从分组移除',
                    danger: true,
                    onClick: () => handleRemoveFromGroup(record.id),
                  }]),
                ],
              }}
              trigger={['click']}
            >
              <Button type="text" size="small" icon={<MoreOutlined style={{ color: '#8c8c8c' }} />} style={{ flexShrink: 0 }} onClick={(e) => e.stopPropagation()} />
            </Dropdown>
          </Flex>

          {/* 角色标签 */}
          <Flex gap={4} align="center" wrap style={{ marginBottom: 4 }}>
            {isMain ? (
              <Tag color="gold" style={{ margin: 0, fontSize: 10, lineHeight: '16px', padding: '0 4px' }}>
                <CrownOutlined style={{ marginRight: 2 }} />创建者
              </Tag>
            ) : isPending ? (
              <Tag color="orange" style={{ margin: 0, fontSize: 10, lineHeight: '16px', padding: '0 4px' }}>
                <ClockCircleOutlined style={{ marginRight: 2 }} />待接受
              </Tag>
            ) : (
              <Tag color="blue" style={{ margin: 0, fontSize: 10, lineHeight: '16px', padding: '0 4px' }}>
                <UserOutlined style={{ marginRight: 2 }} />成员
              </Tag>
            )}
            {isMain && memberCount > 0 && (
              <Tag color="default" style={{ margin: 0, fontSize: 10, lineHeight: '16px', padding: '0 4px' }}>
                <TeamOutlined style={{ marginRight: 2 }} />{Math.max(memberCount - 1, 0)}/5
              </Tag>
            )}
            {record.subscription_status === 'ultra' && (
              <Tag color="purple" style={{ margin: 0, fontSize: 10, lineHeight: '16px', padding: '0 4px' }}>Ultra</Tag>
            )}
            {isRunning && (
              <Tag color="blue" style={{ margin: '0 0 0 auto', fontSize: 10, lineHeight: '16px', padding: '0 4px' }}>运行中</Tag>
            )}
            {isThisAccountRunning && (
              <LoadingOutlined style={{ color: '#1677ff', fontSize: 11, marginLeft: 'auto' }} />
            )}
          </Flex>

          {/* 操作按钮区 */}
          <Flex gap={3} wrap onClick={(e) => e.stopPropagation()}>
            {isPending ? (
              <>
                <Tooltip title="启动并登录">
                  <Button type="text" size="small" disabled={isBrowserLoading || isThisAccountRunning}
                    icon={isBrowserLoading ? <LoadingOutlined style={{ color: '#1677ff' }} />
                      : isRunning ? <PoweroffOutlined style={{ color: '#ff4d4f' }} />
                      : <LoginOutlined style={{ color: '#4285f4' }} />}
                    onClick={() => isRunning ? handleStopBrowser(record.id) : handleLaunchBrowser(record.id)}
                    style={{ padding: '0 4px' }} />
                </Tooltip>
                <Tooltip title="接受邀请">
                  <Button type="text" size="small" disabled={isThisAccountRunning || !isRunning}
                    onClick={() => executeViaWs(record.id, 'family-accept', {}, 'family-accept')}
                    style={{ padding: '0 4px' }}
                    icon={<CheckCircleOutlined style={{ color: (!isThisAccountRunning && isRunning) ? '#52c41a' : '#d9d9d9' }} />} />
                </Tooltip>
              </>
            ) : (
              <>
                <Tooltip title={isBrowserLoading ? '处理中' : isRunning ? '关闭浏览器' : '启动并登录'}>
                  <Button type="text" size="small" disabled={isBrowserLoading || isThisAccountRunning}
                    icon={isBrowserLoading ? <LoadingOutlined style={{ color: '#1677ff' }} />
                      : isRunning ? <PoweroffOutlined style={{ color: '#ff4d4f' }} />
                      : <LoginOutlined style={{ color: '#4285f4' }} />}
                    onClick={() => isRunning ? handleStopBrowser(record.id) : handleLaunchBrowser(record.id)}
                    style={{ padding: '0 4px' }} />
                </Tooltip>
                {record.totp_secret && (
                  <Tooltip title="复制 2FA"><Button type="text" size="small" icon={<CopyOutlined style={{ color: '#52c41a' }} />} onClick={() => copyTOTPCode(record.id)} style={{ padding: '0 4px' }} /></Tooltip>
                )}
                {record.password && (
                  <Tooltip title="复制密码"><Button type="text" size="small" icon={<CopyOutlined style={{ color: '#faad14' }} />} onClick={() => copyToClipboard(record.password, '密码')} style={{ padding: '0 4px' }} /></Tooltip>
                )}
                {profileMap[record.id] && (
                  <Tooltip title="清除浏览器数据"><Button type="text" size="small" disabled={isRunning} icon={<DeleteOutlined style={{ color: isRunning ? '#d9d9d9' : '#ff4d4f' }} />} onClick={() => handleClearBrowserData(record.id)} style={{ padding: '0 4px' }} /></Tooltip>
                )}
                <Tooltip title="OAuth 授权">
                  <Button type="text" size="small" disabled={isThisAccountRunning || !isRunning}
                    icon={(isThisAccountRunning && runningOpKey === 'oauth') ? <LoadingOutlined style={{ color: '#1677ff' }} /> : <SafetyCertificateOutlined style={{ color: (isThisAccountRunning || !isRunning) ? '#d9d9d9' : '#722ed1' }} />}
                    onClick={() => handleOAuth(record.id)} style={{ padding: '0 4px' }} />
                </Tooltip>
                {record.has_oauth_credential && (
                  <>
                    <Tooltip title="复制 OAuth JSON"><Button type="text" size="small" icon={<FileTextOutlined style={{ color: '#1890ff' }} />} onClick={() => handleCopyOAuthJson(record.id)} style={{ padding: '0 4px' }} /></Tooltip>
                    <Tooltip title="下载 OAuth 凭证"><Button type="text" size="small" icon={<DownloadOutlined style={{ color: '#13c2c2' }} />} onClick={() => handleDownloadOAuth(record.id)} style={{ padding: '0 4px' }} /></Tooltip>
                  </>
                )}
                {record.validation_url && (
                  <>
                    <Tooltip title="复制验证链接"><Button type="text" size="small" icon={<LinkOutlined style={{ color: '#ff4d4f' }} />} onClick={() => copyToClipboard(record.validation_url!, '验证链接')} style={{ padding: '0 4px' }} /></Tooltip>
                    <Tooltip title="自动接码验证">
                      <Button type="text" size="small" disabled={isThisAccountRunning || !isRunning}
                        icon={(isThisAccountRunning && runningOpKey === 'phone-verify') ? <LoadingOutlined style={{ color: '#1677ff' }} /> : <PhoneOutlined style={{ color: (isThisAccountRunning || !isRunning) ? '#d9d9d9' : '#fa8c16' }} />}
                        onClick={() => { if (!isRunning) { msg.warning('请先启动浏览器'); return; } executeViaWs(record.id, 'phone-verify', { validation_url: record.validation_url! }, 'phone-verify'); }}
                        style={{ padding: '0 4px' }} />
                    </Tooltip>
                  </>
                )}
                {visibleOps.map((op) => {
                  const needsBrowser = op.needBrowser !== false;
                  const disabled = isThisAccountRunning || (needsBrowser && !isRunning);
                  const isThisOpRunning = isThisAccountRunning && runningOpKey === op.key;
                  return (
                    <Tooltip key={op.key} title={op.label}>
                      <Button type="text" size="small" disabled={disabled && !isThisOpRunning}
                        onClick={() => handleOpClick(record.id, op)} style={{ padding: '0 4px' }}
                        icon={isThisOpRunning ? <LoadingOutlined style={{ color: '#1677ff' }} />
                          : React.cloneElement(op.icon as React.ReactElement<any>, { style: { color: disabled ? '#d9d9d9' : op.color } })} />
                    </Tooltip>
                  );
                })}
              </>
            )}
          </Flex>
        </Card>
      </div>
    );
  };

  /** 渲染右侧日志面板 */
  const renderLogPanel = () => {
    const opState = selectedAccountId ? opStates[selectedAccountId] : null;
    const selectedAccount = selectedAccountId
      ? (group?.accounts || []).find((a) => a.id === selectedAccountId)
      : null;

    return (
      <div style={{
        flex: 1, display: 'flex', flexDirection: 'column',
        border: '1px solid #f0f0f0', borderRadius: 8, background: '#fff',
        minHeight: 0,
      }}>
        {/* 日志头部 */}
        <div style={{ padding: '8px 12px', borderBottom: '1px solid #f0f0f0', flexShrink: 0 }}>
          {selectedAccount ? (
            <Flex align="center" gap={6}>
              <GoogleOutlined style={{ color: '#4285f4', fontSize: 14 }} />
              <Text strong style={{ fontSize: 13 }}>{selectedAccount.email}</Text>
              {opState?.runningOpKey && <Tag color="processing" style={{ margin: 0 }}>{opState.runningOpKey}</Tag>}
            </Flex>
          ) : (
            <Text type="secondary" style={{ fontSize: 12 }}>点击左侧卡片查看日志</Text>
          )}
        </div>
        {/* 日志内容 */}
        <div style={{
          flex: 1, overflowY: 'auto', padding: '8px 12px',
          fontFamily: "'SF Mono', Consolas, monospace", fontSize: 12, lineHeight: '20px',
        }}>
          {opState ? (
            <>
              {opState.steps.length === 0 && opState.runningOpKey && (
                <Flex align="center" gap={6}>
                  <LoadingOutlined style={{ color: '#1677ff', fontSize: 12 }} />
                  <Text type="secondary" style={{ fontSize: 12 }}>等待执行...</Text>
                </Flex>
              )}
              {opState.steps.map((s, i) => (
                <div key={i} style={{ marginBottom: 2 }}>
                  <span style={{
                    color: s.status === 'fail' ? '#ff4d4f'
                      : s.status === 'ok' ? '#52c41a'
                      : s.status === 'skip' ? '#faad14'
                      : '#333',
                    fontWeight: 500,
                  }}>
                    {s.name}
                  </span>
                  {s.message && (
                    /^https?:\/\//.test(s.message) ? (
                      <a href={s.message} target="_blank" rel="noopener noreferrer"
                        style={{ marginLeft: 8, fontSize: 11, color: '#1677ff', wordBreak: 'break-all' }}
                        title={s.message}>
                        {s.message.length > 60 ? s.message.slice(0, 60) + '...' : s.message}
                      </a>
                    ) : (
                      <span style={{ color: '#999', marginLeft: 8 }}>{s.message}</span>
                    )
                  )}
                  {s.duration_ms ? <span style={{ color: '#bbb', marginLeft: 6 }}>({s.duration_ms}ms)</span> : null}
                </div>
              ))}
              {opState.resultMsg && !opState.runningOpKey && (
                <div style={{
                  marginTop: 8, padding: '6px 10px', borderRadius: 6, fontSize: 12,
                  background: opState.resultSuccess ? '#f6ffed' : '#fff2f0',
                  border: `1px solid ${opState.resultSuccess ? '#b7eb8f' : '#ffa39e'}`,
                }}>
                  {opState.resultMsg}
                </div>
              )}
            </>
          ) : (
            <Flex justify="center" align="center" style={{ height: '100%' }}>
              <Text type="secondary" style={{ color: '#d9d9d9' }}>暂无日志</Text>
            </Flex>
          )}
        </div>
      </div>
    );
  };

  // 卡片列表: 主号在前
  const cardAccounts = [
    ...(mainAccount ? [mainAccount] : []),
    ...memberAccounts,
  ];

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      {/* 顶部: 返回 + 分组信息 */}
      <Flex align="center" gap={12} style={{ marginBottom: 12, flexShrink: 0 }}>
        <Button type="text" icon={<ArrowLeftOutlined />} onClick={onBack} />
        <TeamOutlined style={{ color: '#722ed1', fontSize: 20 }} />
        <Text strong style={{ fontSize: 16 }}>{group.name}</Text>
        <Tag color="default" style={{ fontSize: 12 }}>
          {Math.max((group.accounts || []).length - 1, 0)} 个子号
        </Tag>
        {group.notes && <Text type="secondary" style={{ fontSize: 12 }}>{group.notes}</Text>}
        <div style={{ flex: 1 }} />
        <Tooltip title={masked ? '显示邮箱' : '隐藏邮箱'}>
          <Button type="text" icon={masked ? <EyeInvisibleOutlined /> : <EyeOutlined />} onClick={() => setMasked((v) => !v)} />
        </Tooltip>
      </Flex>

      {/* 主体: 左侧卡片列表 + 右侧日志 */}
      <div style={{ flex: 1, display: 'flex', gap: 12, minHeight: 0 }}>
        {/* 左侧: 卡片列表 */}
        <div style={{ width: 380, flexShrink: 0, overflowY: 'auto' }}>
          <Spin spinning={loading}>
            {cardAccounts.length > 0 ? (
              cardAccounts.map((acc) => renderAccountCard(acc, acc.id === group.main_account_id))
            ) : (
              <Empty description="暂无成员" style={{ marginTop: 60 }} />
            )}
          </Spin>
        </div>

        {/* 右侧: 日志面板 */}
        {renderLogPanel()}
      </div>

      {/* 输入字段弹窗 */}
      <Modal
        open={!!activeOp}
        title={activeOp?.label}
        onCancel={() => { setActiveOp(null); setActiveAccountId(null); }}
        onOk={handleFieldModalOk}
        okText="执行"
        cancelText="取消"
        okButtonProps={{ danger: activeOp?.danger }}
        width={420}
        destroyOnClose
      >
        <div style={{ marginTop: 12 }}>
          {/* 邀请: Select tags 模式，粘贴自动拆分 */}
          {activeOp?.key === 'family-invite' && (
            <Select
              mode="tags"
              style={{ width: '100%' }}
              placeholder="输入或粘贴邮箱，回车添加（支持逗号、换行分隔）"
              value={selectedEmails}
              onChange={setSelectedEmails}
              onSearch={handleInviteSearch}
              tokenSeparators={[',', ';', '\n', '\t', ' ']}
              open={false}
              suffixIcon={null}
              notFoundContent={null}
            />
          )}

          {/* 移除: Select 多选，从成员列表选择 */}
          {activeOp?.key === 'family-remove' && (
            <Select
              mode="multiple"
              style={{ width: '100%' }}
              placeholder="选择要移除的成员"
              value={selectedEmails}
              onChange={setSelectedEmails}
              options={getMemberOptions()}
              optionFilterProp="label"
            />
          )}

          {/* 替换: 旧成员下拉选择 + 新成员输入 */}
          {activeOp?.key === 'replace' && (
            <Space direction="vertical" size={12} style={{ width: '100%' }}>
              <Select
                style={{ width: '100%' }}
                placeholder="选择要移除的旧成员"
                value={replaceOldEmail || undefined}
                onChange={setReplaceOldEmail}
                options={getMemberOptions()}
                optionFilterProp="label"
                showSearch
              />
              <Input
                placeholder="新成员邮箱（将被邀请）"
                value={replaceNewEmail}
                onChange={(e) => setReplaceNewEmail(e.target.value)}
                onPressEnter={handleFieldModalOk}
              />
            </Space>
          )}

          {/* 其他操作（如果有 fields，保持原有 Input 模式） */}
          {activeOp && !['family-invite', 'family-remove', 'replace'].includes(activeOp.key) && (
            <Space direction="vertical" size={12} style={{ width: '100%' }}>
              {activeOp.fields?.map((f) => (
                <Input
                  key={f.name}
                  placeholder={f.placeholder}
                  value={formValues[f.name] || ''}
                  onChange={(e) => setFormValues((prev) => ({ ...prev, [f.name]: e.target.value }))}
                  onPressEnter={handleFieldModalOk}
                />
              ))}
            </Space>
          )}
        </div>
      </Modal>

      {/* 添加成员弹窗 */}
      <Modal
        title="添加成员到分组"
        open={addMemberVisible}
        onCancel={() => setAddMemberVisible(false)}
        footer={null}
        width={480}
      >
        {allAccounts.length > 0 ? (
          <Select
            style={{ width: '100%' }}
            placeholder="选择要添加的账号"
            onChange={handleAddAccountToGroup}
            value={undefined}
            showSearch
            optionFilterProp="label"
            options={allAccounts.map((acc) => ({
              label: acc.email,
              value: acc.id,
            }))}
          />
        ) : (
          <Text type="secondary">没有可添加的账号</Text>
        )}
      </Modal>
    </div>
  );
};

export default GroupDetail;
