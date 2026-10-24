import { describe, expect, it, vi } from "vitest";
import { createIntakeVerificationClient, intakeVerificationRequested, type IntakeVerificationRequest } from "../client/intake-verification-client";
import type { ContentBusinessClient } from "../client/runtime";

function baseClient() {
  const forbidden = vi.fn(async (): Promise<never> => { throw new Error("不能调用原生成客户端"); });
  const upload = vi.fn(async () => ({ fileId: "asset_test", filename: "合成资料.txt" }));
  const base: ContentBusinessClient = { list: forbidden, save: forbidden, remove: forbidden, upload, dispatch: forbidden, task: forbidden, stop: forbidden };
  return { base, forbidden, upload };
}
const capability = { module: "content", features: ["subject_workspace", "conversations", "intake"] };
const input = { conversationId: "chat", clientRequestId: "request", prompt: "合成资料，仅验证保存", localAssetIds: [], contentProduction: { mode: "new_reference_pack", enterpriseName: "合成主体", knowledgeSource: "files" } };
const receipt = { id: "request", conversationId: "chat", status: "received", executionStarted: false, acceptedAt: 1,
  conversation: { id: "chat", title: "合成聊天", purpose: "content_production", messages: [], status: "idle", createdAt: 1, updatedAt: 1 } };

describe("显式真实收件验收客户端", () => {
  it("只有精确verify=intake才选择验收入口", () => {
    expect(intakeVerificationRequested("?verify=intake")).toBe(true);
    for (const value of ["", "?preview=intake", "?verify=other", "?verify=INTAKE"]) expect(intakeVerificationRequested(value)).toBe(false);
  });
  it.each([{ module: "content", features: ["tasks"] }, { module: "brand", features: ["intake"] }, null, { module: "content", features: "intake" }])("能力不符时不返回客户端、不回退生成 %j", async value => {
    const { base, forbidden } = baseClient();
    const send = vi.fn().mockResolvedValue(value);
    await expect(createIntakeVerificationClient(base, { request: send as IntakeVerificationRequest })).rejects.toThrow("不会转为生成");
    expect(send).toHaveBeenCalledOnce();
    expect(send.mock.calls[0][0]).toBe("/api/modules/content/capabilities");
    expect(forbidden).not.toHaveBeenCalled();
  });
  it("能力读取失败不写入也不尝试模型", async () => {
    const { base, forbidden, upload } = baseClient();
    const send = vi.fn().mockRejectedValue(new Error("暂时断网"));
    await expect(createIntakeVerificationClient(base, { request: send as IntakeVerificationRequest })).rejects.toThrow("暂时断网");
    expect(forbidden).not.toHaveBeenCalled(); expect(upload).not.toHaveBeenCalled();
  });
  it("验收客户端的派发、任务查询和停止全部本地拒绝，不发送网络请求", async () => {
    const { base, forbidden } = baseClient();
    const send = vi.fn().mockResolvedValue(capability);
    const verified = await createIntakeVerificationClient(base, { request: send as IntakeVerificationRequest });
    await expect(verified.dispatch({})).rejects.toThrow("禁止生成");
    await expect(verified.task("existing-task")).rejects.toThrow("禁止生成");
    await expect(verified.stop("existing-task")).rejects.toThrow("禁止生成");
    expect(send).toHaveBeenCalledOnce(); expect(forbidden).not.toHaveBeenCalled();
    expect(base.submitIntake).toBeUndefined();
  });
  it("只向正式收件路径提交原幂等编号，返回真实回执且不调用原生成端口", async () => {
    const { base, forbidden } = baseClient();
    const send = vi.fn().mockResolvedValueOnce(capability).mockResolvedValueOnce(receipt);
    const verified = await createIntakeVerificationClient(base, { request: send as IntakeVerificationRequest });
    expect(await verified.submitIntake!(input)).toEqual(receipt);
    expect(send.mock.calls[1][0]).toBe("/api/modules/content/intake");
    expect(send.mock.calls[1][1]).toMatchObject({ method: "POST", body: JSON.stringify(input) });
    expect(send).toHaveBeenCalledTimes(2); expect(forbidden).not.toHaveBeenCalled();
  });
  it("回执夹带任务时拒绝，不自动重试和补派发", async () => {
    const { base, forbidden } = baseClient();
    const send = vi.fn().mockResolvedValueOnce(capability).mockResolvedValueOnce({ ...receipt, conversation: { ...receipt.conversation, taskId: "unexpected" } });
    const verified = await createIntakeVerificationClient(base, { request: send as IntakeVerificationRequest });
    await expect(verified.submitIntake!(input)).rejects.toThrow("回执不一致");
    expect(send).toHaveBeenCalledTimes(2); expect(forbidden).not.toHaveBeenCalled();
  });
  it("列表和空聊天保存使用正式存储路径，附件沿用原生上传", async () => {
    const { base, forbidden, upload } = baseClient();
    const send = vi.fn().mockResolvedValueOnce(capability).mockResolvedValueOnce([]).mockResolvedValueOnce(receipt.conversation);
    const verified = await createIntakeVerificationClient(base, { request: send as IntakeVerificationRequest });
    await verified.list(); await verified.save(receipt.conversation as any);
    await verified.upload(new File(["合成资料"], "合成资料.txt"));
    expect(send.mock.calls.slice(1).map(call => call[0])).toEqual(["/api/modules/content/conversations", "/api/modules/content/conversations/chat"]);
    expect(upload).toHaveBeenCalledOnce(); expect(forbidden).not.toHaveBeenCalled();
  });
});
