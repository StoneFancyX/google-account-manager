import React, { useState, useEffect, useRef, useCallback } from 'react';
import {
  Card,
  Input,
  Button,
  Select,
  Table,
  Tag,
  Space,
  Typography,
  Flex,
  App,
  Divider,
  Tooltip,
  Spin,
  Modal,
  List,
  Badge,
  Empty,
} from 'antd';
import {
  SettingOutlined,
  SearchOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
  LoadingOutlined,
  CopyOutlined,
  ReloadOutlined,
  SafetyCertificateOutlined,
  ShoppingCartOutlined,
} from '@ant-design/icons';
import {
  getSmsProviders,
  createSmsProvider,
  updateSmsProvider,
  getSmsBalance,
  requestNumber,
  checkSmsStatus,
  finishSmsActivation,
  cancelSmsActivation,
  getSmsHistory,
  getSmsServices,
  getSmsPricesByService,
  getSettings,
} from '@/api';
import type { SmsProviderConfig, SmsActivationRecord } from '@/api/sms';

const { Text } = Typography;

const PROVIDER_TYPES = [
  { value: 'herosms', label: 'HeroSMS' },
  { value: 'smsbus', label: 'SMS-Bus' },
];

const STATUS_MAP: Record<string, { color: string; label: string }> = {
  pending: { color: 'processing', label: '等待验证码' },
  code_received: { color: 'success', label: '已收到' },
  finished: { color: 'default', label: '已完成' },
  cancelled: { color: 'warning', label: '已取消' },
  error: { color: 'error', label: '错误' },
};

interface CountryPrice {
  country_id: number;
  country_name: string;
  phone_code: string;
  count: number;
  price: string;
}

const SmsPage: React.FC = () => {
  const { message: msg } = App.useApp();

  // 配置弹窗
  const [configOpen, setConfigOpen] = useState(false);
  const [configType, setConfigType] = useState('herosms');
  const [configApiKey, setConfigApiKey] = useState('');
  const [configTesting, setConfigTesting] = useState(false);
  const [configTestResult, setConfigTestResult] = useState<{ ok: boolean; msg: string } | null>(null);
  const [configSaving, setConfigSaving] = useState(false);
  const [providers, setProviders] = useState<SmsProviderConfig[]>([]);
  const [defaultProviderId, setDefaultProviderId] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [configCountry, setConfigCountry] = useState<number | string>(2);
  const [configService, setConfigService] = useState('go');
  const [configCountries, setConfigCountries] = useState<{ value: number | string; label: string }[]>([]);
  const [configCountryLoading, setConfigCountryLoading] = useState(false);

  // 左侧: 国家列表 (基于默认服务)
  const [services, setServices] = useState<{ code: string; name: string }[]>([]);
  const [countrySearch, setCountrySearch] = useState('');
  const [countryPrices, setCountryPrices] = useState<CountryPrice[]>([]);
  const [countryLoading, setCountryLoading] = useState(false);
  const [countrySortBy, setCountrySortBy] = useState<'count' | 'price'>('count');

  // 接码
  const [buyLoading, setBuyLoading] = useState<string | null>(null); // country_id loading
  const [activeActivation, setActiveActivation] = useState<{
    activation_id: string; phone_number: string; cost: string; status: string; code: string; provider_id: number; service: string;
  } | null>(null);
  const [polling, setPolling] = useState(false);
  const pollTimer = useRef<ReturnType<typeof setInterval> | null>(null);

  // 历史
  const [history, setHistory] = useState<SmsActivationRecord[]>([]);
  const [historyTotal, setHistoryTotal] = useState(0);
  const [historyPage, setHistoryPage] = useState(1);
  const [historyLoading, setHistoryLoading] = useState(false);

  useEffect(() => {
    loadAll();
    loadHistory(1);
    return () => { if (pollTimer.current) clearInterval(pollTimer.current); };
  }, []);

  const loadAll = async () => {
    setLoading(true);
    try {
      const [provRes, settingsRes] = await Promise.all([getSmsProviders(), getSettings()]);
      setProviders(provRes.data);
      const defId = settingsRes.data.default_sms_provider_id ? Number(settingsRes.data.default_sms_provider_id) : null;
      setDefaultProviderId(defId);
      const activeProvider = defId ? provRes.data.find((p) => p.id === defId) : provRes.data[0];
      if (activeProvider?.api_key) {
        loadServices(activeProvider.id);
        loadCountryPrices(activeProvider.default_service || 'go', activeProvider.id);
      }
    } catch { /* silent */ }
    finally { setLoading(false); }
  };

  const getActiveProvider = () => {
    if (defaultProviderId) return providers.find((p) => p.id === defaultProviderId);
    return providers[0];
  };

  const loadServices = async (providerId: number) => {
    try {
      const { data } = await getSmsServices(providerId);
      setServices(Array.isArray(data) ? data : []);
    } catch { /* silent */ }
  };

  const loadCountryPrices = async (service: string, providerId: number) => {
    setCountryLoading(true);
    try {
      const { data } = await getSmsPricesByService(service, providerId);
      setCountryPrices(Array.isArray(data) ? data : []);
    } catch { setCountryPrices([]); }
    finally { setCountryLoading(false); }
  };

  // ── 配置弹窗 ────────────────────────────────────────

  const openConfig = () => {
    const existing = providers.find((p) => p.provider_type === configType);
    setConfigApiKey(existing?.api_key || '');
    setConfigCountry(existing?.default_country ?? 2);
    setConfigService(existing?.default_service || 'go');
    setConfigTestResult(null);
    setConfigOpen(true);
    // 有 API Key → 加载该服务的国家列表
    if (existing?.api_key && existing.default_service) {
      loadConfigCountries(existing.default_service, existing.id);
    } else {
      setConfigCountries([]);
    }
  };

  const handleConfigTypeChange = (type: string) => {
    setConfigType(type);
    setConfigTestResult(null);
    const existing = providers.find((p) => p.provider_type === type);
    setConfigApiKey(existing?.api_key || '');
    setConfigCountry(existing?.default_country ?? 2);
    setConfigService(existing?.default_service || 'go');
    if (existing?.api_key && existing.default_service) {
      loadConfigCountries(existing.default_service, existing.id);
    } else {
      setConfigCountries([]);
    }
  };

  const handleConfigServiceChange = (svc: string) => {
    setConfigService(svc);
    const existing = providers.find((p) => p.provider_type === configType);
    if (existing?.api_key) loadConfigCountries(svc, existing.id);
  };

  const loadConfigCountries = async (service: string, providerId: number) => {
    setConfigCountryLoading(true);
    setConfigCountries([]);
    try {
      const { data } = await getSmsPricesByService(service, providerId);
      setConfigCountries(
        (Array.isArray(data) ? data : [])
          .filter((c: any) => c.count > 0)
          .map((c: any) => ({
            value: c.country_id,
            label: `${c.country_name}${c.phone_code ? ' (' + c.phone_code + ')' : ''} - $${c.price} (${c.count})`,
          }))
      );
    } catch { /* silent */ }
    finally { setConfigCountryLoading(false); }
  };

  const handleTestApiKey = async () => {
    if (!configApiKey.trim()) { msg.warning('请输入 API Key'); return; }
    setConfigTesting(true);
    setConfigTestResult(null);
    try {
      const existing = providers.find((p) => p.provider_type === configType);
      let provider: SmsProviderConfig;
      if (existing) {
        const { data } = await updateSmsProvider(existing.id, { api_key: configApiKey });
        provider = data;
      } else {
        const typeName = PROVIDER_TYPES.find((t) => t.value === configType)?.label || configType;
        const { data } = await createSmsProvider({ name: typeName, provider_type: configType, api_key: configApiKey });
        provider = data;
      }
      const { data: balData } = await getSmsBalance(provider.id);
      setConfigTestResult({ ok: true, msg: `有效，余额: $${balData.balance}` });
      const { data: newProviders } = await getSmsProviders();
      setProviders(newProviders);
      // 加载服务列表和当前服务的国家列表
      loadServices(provider.id);
      loadConfigCountries(configService, provider.id);
    } catch (err: any) {
      setConfigTestResult({ ok: false, msg: err.response?.data?.detail || '测试失败' });
    } finally { setConfigTesting(false); }
  };

  const handleSaveConfig = async () => {
    if (!configApiKey.trim()) { msg.warning('请输入 API Key'); return; }
    setConfigSaving(true);
    try {
      const existing = providers.find((p) => p.provider_type === configType);
      if (existing) {
        await updateSmsProvider(existing.id, { api_key: configApiKey, default_country: Number(configCountry), default_service: String(configService) });
      } else {
        const typeName = PROVIDER_TYPES.find((t) => t.value === configType)?.label || configType;
        await createSmsProvider({ name: typeName, provider_type: configType, api_key: configApiKey, default_country: Number(configCountry), default_service: String(configService) });
      }
      msg.success('配置已保存');
      setConfigOpen(false);
      loadAll();
    } catch (err: any) { msg.error(err.response?.data?.detail || '保存失败'); }
    finally { setConfigSaving(false); }
  };

  // ── 接码操作 ────────────────────────────────────────

  const handleBuyNumber = async (serviceCode: string, countryId: number) => {
    const provider = getActiveProvider();
    if (!provider) { msg.warning('请先配置提供商'); return; }
    const key = `${countryId}`;
    setBuyLoading(key);
    try {
      const { data } = await requestNumber({ provider_id: provider.id, service: serviceCode, country: countryId });
      setActiveActivation({ activation_id: data.activation_id, phone_number: data.phone_number, cost: data.cost, status: 'pending', code: '', provider_id: provider.id, service: serviceCode });
      msg.success(`号码: ${data.phone_number}`);
      startPolling(data.activation_id, provider.id);
    } catch (err: any) { msg.error(err.response?.data?.detail || '购买失败'); }
    finally { setBuyLoading(null); }
  };

  const startPolling = useCallback((activationId: string, providerId: number) => {
    if (pollTimer.current) clearInterval(pollTimer.current);
    setPolling(true);
    pollTimer.current = setInterval(async () => {
      try {
        const { data } = await checkSmsStatus(activationId, providerId);
        if (data.code) {
          setActiveActivation((prev) => prev ? { ...prev, status: 'code_received', code: data.code } : null);
          if (pollTimer.current) clearInterval(pollTimer.current);
          setPolling(false);
          msg.success(`验证码: ${data.code}`);
          loadHistory(1);
        } else if (data.status === 'CANCEL') {
          setActiveActivation((prev) => prev ? { ...prev, status: 'cancelled' } : null);
          if (pollTimer.current) clearInterval(pollTimer.current);
          setPolling(false);
          loadHistory(1);
        }
      } catch { /* silent */ }
    }, 5000);
  }, [msg]);

  const handleFinish = async () => {
    if (!activeActivation) return;
    try { await finishSmsActivation(activeActivation.activation_id, activeActivation.provider_id); setActiveActivation((prev) => prev ? { ...prev, status: 'finished' } : null); msg.success('已完成'); loadHistory(1); }
    catch (err: any) { msg.error(err.response?.data?.detail || '失败'); }
  };

  const handleCancel = async () => {
    if (!activeActivation) return;
    try { await cancelSmsActivation(activeActivation.activation_id, activeActivation.provider_id); setActiveActivation((prev) => prev ? { ...prev, status: 'cancelled' } : null); if (pollTimer.current) clearInterval(pollTimer.current); setPolling(false); msg.success('已取消'); loadHistory(1); }
    catch (err: any) { msg.error(err.response?.data?.detail || '失败'); }
  };

  const handleHistoryCancel = async (record: SmsActivationRecord) => {
    try {
      await cancelSmsActivation(record.activation_id, record.provider_id ?? undefined);
      msg.success('已取消');
      // 如果取消的是当前激活的号码，同步更新
      if (activeActivation?.activation_id === record.activation_id) {
        setActiveActivation((prev) => prev ? { ...prev, status: 'cancelled' } : null);
        if (pollTimer.current) clearInterval(pollTimer.current);
        setPolling(false);
      }
      loadHistory(historyPage);
    } catch (err: any) { msg.error(err.response?.data?.detail || '取消失败'); }
  };

  const handleHistoryFinish = async (record: SmsActivationRecord) => {
    try {
      await finishSmsActivation(record.activation_id, record.provider_id ?? undefined);
      msg.success('已完成');
      if (activeActivation?.activation_id === record.activation_id) {
        setActiveActivation((prev) => prev ? { ...prev, status: 'finished' } : null);
      }
      loadHistory(historyPage);
    } catch (err: any) { msg.error(err.response?.data?.detail || '完成失败'); }
  };

  const copyText = (text: string, label: string) => navigator.clipboard.writeText(text).then(() => msg.success(`${label}已复制`));

  const loadHistory = async (page: number) => {
    setHistoryLoading(true);
    try { const { data } = await getSmsHistory(page, 15); setHistory(data.records); setHistoryTotal(data.total); setHistoryPage(page); }
    catch { /* silent */ }
    finally { setHistoryLoading(false); }
  };

  if (loading) return <div style={{ textAlign: 'center', padding: '100px 0' }}><Spin size="large" /></div>;

  const activeProvider = getActiveProvider();
  const defaultService = activeProvider?.default_service || 'go';
  const filteredCountries = countrySearch
    ? countryPrices.filter((cp) => cp.country_name.toLowerCase().includes(countrySearch.toLowerCase()) || cp.phone_code.includes(countrySearch))
    : countryPrices;
  const sortedCountries = [...filteredCountries]
    .sort((a, b) => countrySortBy === 'price' ? parseFloat(a.price) - parseFloat(b.price) : b.count - a.count)
    .filter((cp) => cp.count > 0);

  return (
    <div style={{ display: 'flex', height: '100%', gap: 12 }}>
      {/* 左侧: 国家列表 */}
      <div style={{ width: 340, flexShrink: 0, display: 'flex', flexDirection: 'column', height: '100%' }}>
        <Flex align="center" gap={8} style={{ marginBottom: 8 }}>
          <Input
            size="small"
            placeholder="搜索国家..."
            prefix={<SearchOutlined style={{ color: '#bfbfbf' }} />}
            value={countrySearch}
            onChange={(e) => setCountrySearch(e.target.value)}
            allowClear
            style={{ flex: 1 }}
          />
          <Flex gap={4}>
            <Text
              style={{ fontSize: 11, cursor: 'pointer', color: countrySortBy === 'count' ? '#1677ff' : '#999', whiteSpace: 'nowrap' }}
              onClick={() => setCountrySortBy('count')}
            >数量↓</Text>
            <Text
              style={{ fontSize: 11, cursor: 'pointer', color: countrySortBy === 'price' ? '#1677ff' : '#999', whiteSpace: 'nowrap' }}
              onClick={() => setCountrySortBy('price')}
            >价格↑</Text>
          </Flex>
          <Tooltip title="配置">
            <Button size="small" icon={<SettingOutlined />} onClick={openConfig} />
          </Tooltip>
        </Flex>

        <div style={{ flex: 1, overflowY: 'auto', border: '1px solid #f0f0f0', borderRadius: 8, background: '#fff' }}>
          {!activeProvider?.api_key ? (
            <Empty description="请先配置提供商" image={Empty.PRESENTED_IMAGE_SIMPLE} style={{ marginTop: 40 }} />
          ) : countryLoading ? (
            <div style={{ padding: 40, textAlign: 'center' }}><Spin /></div>
          ) : sortedCountries.length === 0 ? (
            <Empty description="暂无可用号码" image={Empty.PRESENTED_IMAGE_SIMPLE} style={{ marginTop: 40 }} />
          ) : (
            sortedCountries.map((cp) => (
              <div key={cp.country_id}
                className="hover-card"
                style={{
                  padding: '7px 12px',
                  display: 'flex', alignItems: 'center', gap: 8,
                  borderBottom: '1px solid #f5f5f5',
                  cursor: 'pointer',
                  transition: 'background 0.15s',
                }}
                onMouseEnter={(e) => (e.currentTarget.style.background = '#e6f4ff')}
                onMouseLeave={(e) => (e.currentTarget.style.background = 'transparent')}
                onClick={() => handleBuyNumber(defaultService, cp.country_id)}
              >
                <Text ellipsis style={{ flex: 1, fontSize: 12 }}>
                  {cp.country_name}
                  {cp.phone_code && <Text type="secondary" style={{ fontSize: 11 }}> ({cp.phone_code})</Text>}
                </Text>
                <Tag style={{ margin: 0, fontSize: 11 }}>{cp.count}</Tag>
                <Text type="secondary" style={{ fontSize: 11, minWidth: 45, textAlign: 'right' }}>${cp.price}</Text>
                {buyLoading === `${cp.country_id}` ? (
                  <LoadingOutlined style={{ fontSize: 16, color: '#1677ff' }} />
                ) : (
                  <ShoppingCartOutlined style={{ fontSize: 16, color: '#52c41a', transition: 'all 0.2s' }}
                    onMouseEnter={(e) => { e.currentTarget.style.fontSize = '20px'; e.currentTarget.style.color = '#389e0d'; }}
                    onMouseLeave={(e) => { e.currentTarget.style.fontSize = '16px'; e.currentTarget.style.color = '#52c41a'; }}
                  />
                )}
              </div>
            ))
          )}
        </div>
      </div>

      {/* 右侧: 当前激活 + 历史 */}
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0, height: '100%' }}>
        {/* 当前激活 */}
        {activeActivation && (
          <Card size="small" style={{ marginBottom: 12, flexShrink: 0 }} styles={{ body: { padding: '8px 16px' } }}>
            <Flex gap={16} align="center" wrap>
              <Flex gap={6} align="center">
                <Text type="secondary">号码:</Text>
                <Text strong copyable style={{ fontFamily: 'monospace' }}>{activeActivation.phone_number}</Text>
                {activeActivation.cost && <Tag color="blue">${activeActivation.cost}</Tag>}
                <Tag>{activeActivation.service}</Tag>
              </Flex>
              <Flex gap={6} align="center">
                <Text type="secondary">验证码:</Text>
                {activeActivation.code ? (
                  <Tag color="green" style={{ fontSize: 16, padding: '2px 12px', cursor: 'pointer', fontFamily: 'monospace' }}
                    onClick={() => copyText(activeActivation.code, '验证码')}>
                    {activeActivation.code} <CopyOutlined style={{ marginLeft: 6 }} />
                  </Tag>
                ) : polling ? (
                  <Space size={4}><LoadingOutlined style={{ color: '#1677ff' }} /><Text type="secondary">等待中...</Text></Space>
                ) : <Text type="secondary">-</Text>}
              </Flex>
              <Space size={4} style={{ marginLeft: 'auto' }}>
                {activeActivation.status === 'code_received' && (
                  <Button size="small" type="primary" icon={<CheckCircleOutlined />} onClick={handleFinish}>完成</Button>
                )}
                {['pending', 'code_received'].includes(activeActivation.status) && (
                  <Button size="small" danger icon={<CloseCircleOutlined />} onClick={handleCancel}>取消</Button>
                )}
                {['finished', 'cancelled'].includes(activeActivation.status) && (
                  <Button size="small" onClick={() => setActiveActivation(null)}>清除</Button>
                )}
              </Space>
            </Flex>
          </Card>
        )}

        {/* 历史表格 */}
        <Card size="small" style={{ flex: 1, display: 'flex', flexDirection: 'column', minHeight: 0 }}
          title="接码记录"
          extra={
            <Space size={8}>
              {activeProvider && <Tag color="green">${activeProvider.balance || '—'}</Tag>}
              <Button size="small" type="text" icon={<ReloadOutlined />} onClick={() => loadHistory(historyPage)} />
            </Space>
          }
          styles={{ body: { flex: 1, padding: 0, overflow: 'hidden' } }}>
          <Table dataSource={history} rowKey="id" size="small" loading={historyLoading}
            scroll={{ y: 'calc(100vh - 220px)' }}
            pagination={{ current: historyPage, total: historyTotal, pageSize: 15, size: 'small', showTotal: (t) => `共 ${t} 条`, onChange: loadHistory }}
            columns={[
              { title: '号码', dataIndex: 'phone_number', width: 155,
                render: (v: string) => <Tooltip title="点击复制"><Text style={{ cursor: 'pointer', fontFamily: 'monospace', fontSize: 12 }} onClick={() => copyText(v, '号码')}>{v}</Text></Tooltip> },
              { title: '验证码', dataIndex: 'sms_code', width: 95,
                render: (v: string) => v ? <Tag color="green" style={{ cursor: 'pointer', fontFamily: 'monospace' }} onClick={() => copyText(v, '验证码')}>{v}</Tag> : '-' },
              { title: '服务', dataIndex: 'service', width: 70, render: (v: string) => <Tag>{v}</Tag> },
              { title: '费用', dataIndex: 'cost', width: 70, render: (v: string) => v ? `$${v}` : '-' },
              { title: '状态', dataIndex: 'status', width: 95,
                render: (v: string) => { const s = STATUS_MAP[v] || { color: 'default', label: v }; return <Tag color={s.color}>{s.label}</Tag>; } },
              { title: '时间', dataIndex: 'created_at', width: 150, render: (v: string) => v ? new Date(v).toLocaleString('zh-CN') : '-' },
              { title: '操作', width: 100, render: (_: any, record: SmsActivationRecord) => (
                <Space size={4}>
                  {record.status === 'pending' && (
                    <Tooltip title="取消"><Button type="text" size="small" danger icon={<CloseCircleOutlined />} onClick={() => handleHistoryCancel(record)} /></Tooltip>
                  )}
                  {record.status === 'code_received' && (
                    <>
                      <Tooltip title="完成"><Button type="text" size="small" icon={<CheckCircleOutlined style={{ color: '#52c41a' }} />} onClick={() => handleHistoryFinish(record)} /></Tooltip>
                      <Tooltip title="取消"><Button type="text" size="small" danger icon={<CloseCircleOutlined />} onClick={() => handleHistoryCancel(record)} /></Tooltip>
                    </>
                  )}
                </Space>
              )},
            ]}
          />
        </Card>
      </div>

      {/* 配置弹窗 */}
      <Modal open={configOpen} title="接码配置" onCancel={() => setConfigOpen(false)}
        onOk={handleSaveConfig} okText="保存" cancelText="取消" confirmLoading={configSaving}
        width={480}>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 14, marginTop: 16 }}>
          <div>
            <Text strong>提供商</Text>
            <Select style={{ width: '100%', marginTop: 4 }} value={configType}
              onChange={handleConfigTypeChange} options={PROVIDER_TYPES} />
          </div>
          <div>
            <Text strong>API Key</Text>
            <Flex gap={8} style={{ marginTop: 4 }}>
              <Input.Password placeholder="输入 API Key" value={configApiKey}
                onChange={(e) => { setConfigApiKey(e.target.value); setConfigTestResult(null); }}
                style={{ flex: 1 }} />
              <Button icon={<SafetyCertificateOutlined />} loading={configTesting} onClick={handleTestApiKey}>
                测试
              </Button>
            </Flex>
            {configTestResult && (
              <Text type={configTestResult.ok ? 'success' : 'danger'} style={{ fontSize: 12, marginTop: 4, display: 'block' }}>
                {configTestResult.msg}
              </Text>
            )}
          </div>
          <Flex gap={16}>
            <div style={{ flex: 1 }}>
              <Text strong>默认服务</Text>
              <Select style={{ width: '100%', marginTop: 4 }} value={configService}
                onChange={handleConfigServiceChange}
                options={services.map((s) => ({ value: s.code, label: `${s.name} (${s.code})` }))}
                showSearch optionFilterProp="label"
                placeholder="选择服务" />
            </div>
            <div style={{ flex: 1 }}>
              <Text strong>默认国家</Text>
              <Select style={{ width: '100%', marginTop: 4 }} value={configCountry}
                onChange={setConfigCountry}
                options={configCountries}
                showSearch optionFilterProp="label"
                loading={configCountryLoading} placeholder="先选择服务" />
            </div>
          </Flex>
        </div>
      </Modal>
    </div>
  );
};

export default SmsPage;
