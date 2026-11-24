# test_mcp_client.py
import asyncio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

async def main():
    server_params = StdioServerParameters(command="python", args=["mcp_server.py"])
    
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            # 1. 初始化握手
            await session.initialize()
            
            # 2. 发现工具
            tools = await session.list_tools()
            print("🤖 发现可用工具:", [t.name for t in tools.tools])
            
            # 3. 提交生成任务
            print("\n🚀 正在请求生成视频（主题：地球为什么是圆的）...")
            result = await session.call_tool("generate_video", arguments={"topic": "地球为什么是圆的"})
            response_text = result.content[0].text
            print("📩 工具返回:", response_text)
            
            # 提取 task_id
            task_id = response_text.split("任务ID: ")[1].split("。")[0]
            
            # 4. 🚨 关键修改：轮询等待任务完成，防止客户端提前退出
            print(f"\n⏳ 开始轮询任务 {task_id} 的状态...")
            while True:
                status_res = await session.call_tool("get_task_status", arguments={"task_id": task_id})
                # MCP 返回的 dict 内容可能会被转为字符串，这里简单判断
                status_text = str(status_res.content[0].text) 
                print(f"  -> 当前状态: {status_text}")
                
                if "'status': 'completed'" in status_text or '"status": "completed"' in status_text:
                    print("\n✅ 视频渲染完成！")
                    break
                elif "'status': 'failed'" in status_text or '"status": "failed"' in status_text:
                    print("\n❌ 视频渲染失败！")
                    break
                
                # 休息 5 秒后再查
                await asyncio.sleep(5)

if __name__ == "__main__":
    asyncio.run(main())