#!/usr/bin/env node
// fusion_mcp_server.js - Version adaptée pour fusion_mcp_server.py japonais v0.7.82
import fs from 'fs/promises';
import path from 'path';
import os from 'os';
import { Server } from '@modelcontextprotocol/sdk/server/index.js';
import { StdioServerTransport } from '@modelcontextprotocol/sdk/server/stdio.js';
import {
    CallToolRequestSchema,
    ErrorCode,
    ListToolsRequestSchema,
    McpError,
} from '@modelcontextprotocol/sdk/types.js';

const logDebug = (message, ...args) => {
    console.error(`[FUSION-MCP-JAPANESE] ${new Date().toISOString()} - ${message}`, ...args);
};

const commandFilePath = path.join(os.homedir(), 'Documents', 'fusion_command.txt');
const responseFilePath = path.join(os.homedir(), 'Documents', 'fusion_response.txt');

class JapaneseFusion360MCPServer {
    constructor() {
        logDebug('Initializing Japanese Fusion360 MCP Server...');
        this.server = new Server(
            {
                name: 'fusion-mcp-server-japanese-adapted',
                version: '0.7.82',
            },
            {
                capabilities: {
                    tools: {},
                },
            }
        );
        
        this.setupToolHandlers();
        logDebug('Japanese server constructor finished.');
    }
    
    safeNumberConvert(value, defaultValue = 0, min = -Infinity, max = Infinity) {
        if (value === undefined || value === null) return defaultValue;
        if (typeof value === 'string' && value.trim() === '') return defaultValue;
        const num = Number(value);
        if (isNaN(num)) {
            logDebug(`Invalid number value: ${value}, using default: ${defaultValue}`);
            return defaultValue;
        }
        return Math.max(min, Math.min(max, num));
    }
    
    safeIntegerConvert(value, defaultValue = 1, min = 1, max = 1000) {
        const num = this.safeNumberConvert(value, defaultValue, min, max);
        return Math.round(num);
    }

    async waitForResponseFileUpdate(timeout = 60000) {
        logDebug('Waiting for fusion_response.txt to be updated...');
        const startTime = Date.now();
        const pollInterval = 100;

        while (Date.now() - startTime < timeout) {
            try {
                const stats = await fs.stat(responseFilePath);
                if (stats.size > 0) {
                    await new Promise(resolve => setTimeout(resolve, 50));
                    const content = await fs.readFile(responseFilePath, 'utf8');
                    if (content.trim().length > 0) {
                        logDebug('Successfully read response file content');
                        return content.trim();
                    }
                }
            } catch (error) {
                // ファイルが存在しないか、アクセスできない場合は次のポーリングで再試行
            }
            await new Promise(resolve => setTimeout(resolve, pollInterval));
        }
        
        logDebug('Timeout waiting for fusion_response.txt update');
        throw new Error(`Timeout waiting for Fusion 360 response (${timeout}ms)`);
    }

    async clearResponseFile() {
        try {
            await fs.writeFile(responseFilePath, '', 'utf8');
            logDebug('Successfully cleared fusion_response.txt');
        } catch (error) {
            logDebug('Error clearing fusion_response.txt:', error);
        }
    }
    
    setupToolHandlers() {
        logDebug('Setting up Japanese-adapted tool handlers...');
        
        this.server.setRequestHandler(ListToolsRequestSchema, async () => {
            logDebug('ListToolsRequest received for Japanese version.');
            const tools = [
                // === Macro Tool ===
                {
                    name: 'execute_macro',
                    description: '複数のモデリングコマンドを順番に実行します。',
                    inputSchema: {
                        type: 'object',
                        properties: {
                            commands: {
                                type: 'array',
                                description: '実行するコマンドオブジェクトの配列。',
                                items: {
                                    type: 'object',
                                    properties: {
                                        tool_name: { type: 'string', description: '呼び出すツールの名前。' },
                                        arguments: { type: 'object', description: 'そのツールに渡す引数。' }
                                    },
                                    required: ['tool_name']
                                }
                            }
                        },
                        required: ['commands']
                    }
                },
                // === Primitive Creation Tools (Japanese version) ===
                {
                    name: 'create_cube',
                    description: '立方体を作成します。配置オプションで底面/中心/上面を指定できます。',
                    inputSchema: {
                        type: 'object',
                        properties: {
                            size: { type: 'number', default: 50, description: '立方体の辺の長さ (mm)。' },
                            body_name: { type: 'string', description: '作成されるボディの名前（任意）。' },
                            plane: { type: 'string', enum: ['xy', 'xz', 'yz'], default: 'xy', description: '基準平面。' },
                            cx: { type: 'number', default: 0, description: '中心のX座標 (mm)。' },
                            cy: { type: 'number', default: 0, description: '中心のY座標 (mm)。' },
                            cz: { type: 'number', default: 0, description: '中心のZ座標 (mm)。' },
                            z_placement: { type: 'string', enum: ['center', 'bottom', 'top'], default: 'center', description: 'Z軸方向の配置基準。' },
                            x_placement: { type: 'string', enum: ['center', 'left', 'right'], default: 'center', description: 'X軸方向の配置基準。' },
                            y_placement: { type: 'string', enum: ['center', 'front', 'back'], default: 'center', description: 'Y軸方向の配置基準。' },
                            taper_angle: { type: 'number', default: 0, description: 'テーパー角度（度）。' },
                            taper_direction: { type: 'string', enum: ['inward', 'outward'], default: 'inward', description: 'テーパーの方向。' },
                            direction: { type: 'string', enum: ['positive', 'negative'], default: 'positive', description: '押し出し方向。' }
                        }
                    }
                },
                {
                    name: 'create_cylinder',
                    description: '円柱を作成します。配置オプションで底面/中心/上面を指定できます。',
                    inputSchema: {
                        type: 'object',
                        properties: {
                            radius: { type: 'number', default: 25, description: '円柱の半径 (mm)。' },
                            height: { type: 'number', default: 50, description: '円柱の高さ (mm)。' },
                            body_name: { type: 'string', description: '作成されるボディの名前（任意）。' },
                            plane: { type: 'string', enum: ['xy', 'xz', 'yz'], default: 'xy', description: '基準平面。' },
                            cx: { type: 'number', default: 0, description: '中心のX座標 (mm)。' },
                            cy: { type: 'number', default: 0, description: '中心のY座標 (mm)。' },
                            cz: { type: 'number', default: 0, description: '中心のZ座標 (mm)。' },
                            z_placement: { type: 'string', enum: ['center', 'bottom', 'top'], default: 'center', description: 'Z軸方向の配置基準。' },
                            x_placement: { type: 'string', enum: ['center', 'left', 'right'], default: 'center', description: 'X軸方向の配置基準。' },
                            y_placement: { type: 'string', enum: ['center', 'front', 'back'], default: 'center', description: 'Y軸方向の配置基準。' },
                            taper_angle: { type: 'number', default: 0, description: 'テーパー角度（度）。' },
                            taper_direction: { type: 'string', enum: ['inward', 'outward'], default: 'inward', description: 'テーパーの方向。' },
                            direction: { type: 'string', enum: ['positive', 'negative'], default: 'positive', description: '押し出し方向。' }
                        }
                    }
                },
                {
                    name: 'create_box',
                    description: '直方体を作成します。配置オプションで底面/中心/上面を指定できます。',
                    inputSchema: {
                        type: 'object',
                        properties: {
                            width: { type: 'number', default: 50, description: '幅 (X軸) (mm)。' },
                            depth: { type: 'number', default: 30, description: '奥行 (Y軸) (mm)。' },
                            height: { type: 'number', default: 20, description: '高さ (Z軸) (mm)。' },
                            body_name: { type: 'string', description: '作成されるボディの名前（任意）。' },
                            plane: { type: 'string', enum: ['xy', 'xz', 'yz'], default: 'xy', description: '基準平面。' },
                            cx: { type: 'number', default: 0, description: '中心のX座標 (mm)。' },
                            cy: { type: 'number', default: 0, description: '中心のY座標 (mm)。' },
                            cz: { type: 'number', default: 0, description: '中心のZ座標 (mm)。' },
                            z_placement: { type: 'string', enum: ['center', 'bottom', 'top'], default: 'center', description: 'Z軸方向の配置基準。' },
                            x_placement: { type: 'string', enum: ['center', 'left', 'right'], default: 'center', description: 'X軸方向の配置基準。' },
                            y_placement: { type: 'string', enum: ['center', 'front', 'back'], default: 'center', description: 'Y軸方向の配置基準。' },
                            taper_angle: { type: 'number', default: 0, description: 'テーパー角度（度）。' },
                            taper_direction: { type: 'string', enum: ['inward', 'outward'], default: 'inward', description: 'テーパーの方向。' },
                            direction: { type: 'string', enum: ['positive', 'negative'], default: 'positive', description: '押し出し方向。' }
                        }
                    }
                },
                {
                    name: 'create_sphere',
                    description: '球を作成します。配置は常に中心基準です。',
                    inputSchema: {
                        type: 'object',
                        properties: {
                            radius: { type: 'number', default: 25, description: '球の半径 (mm)。' },
                            body_name: { type: 'string', description: '作成されるボディの名前（任意）。' },
                            cx: { type: 'number', default: 0, description: '中心のX座標 (mm)。' },
                            cy: { type: 'number', default: 0, description: '中心のY座標 (mm)。' },
                            cz: { type: 'number', default: 0, description: '中心のZ座標 (mm)。' }
                        }
                    }
                },
                {
                    name: 'create_hemisphere',
                    description: '半球を作成します。',
                    inputSchema: {
                        type: 'object',
                        properties: {
                            radius: { type: 'number', default: 25, description: '半球の半径 (mm)。' },
                            body_name: { type: 'string', description: '作成されるボディの名前（任意）。' },
                            plane: { type: 'string', enum: ['xy', 'xz', 'yz'], default: 'xy', description: '基準平面。' },
                            cx: { type: 'number', default: 0, description: '中心のX座標 (mm)。' },
                            cy: { type: 'number', default: 0, description: '中心のY座標 (mm)。' },
                            cz: { type: 'number', default: 0, description: '中心のZ座標 (mm)。' },
                            orientation: { type: 'string', enum: ['positive', 'negative'], default: 'positive', description: '半球の向き。' },
                            z_placement: { type: 'string', enum: ['bottom', 'center', 'top'], default: 'bottom', description: '配置基準。' },
                            x_placement: { type: 'string', enum: ['center', 'left', 'right'], default: 'center', description: 'X軸方向の配置基準。' },
                            y_placement: { type: 'string', enum: ['center', 'front', 'back'], default: 'center', description: 'Y軸方向の配置基準。' }
                        }
                    }
                },
                {
                    name: 'create_cone',
                    description: '円錐を作成します。',
                    inputSchema: {
                        type: 'object',
                        properties: {
                            radius: { type: 'number', default: 25, description: '円錐の底面半径 (mm)。' },
                            height: { type: 'number', default: 50, description: '円錐の高さ (mm)。' },
                            body_name: { type: 'string', description: '作成されるボディの名前（任意）。' },
                            plane: { type: 'string', enum: ['xy', 'xz', 'yz'], default: 'xy', description: '基準平面。' },
                            cx: { type: 'number', default: 0, description: '中心のX座標 (mm)。' },
                            cy: { type: 'number', default: 0, description: '中心のY座標 (mm)。' },
                            cz: { type: 'number', default: 0, description: '中心のZ座標 (mm)。' },
                            z_placement: { type: 'string', enum: ['center', 'bottom', 'top'], default: 'center', description: '配置基準。' },
                            x_placement: { type: 'string', enum: ['center', 'left', 'right'], default: 'center', description: 'X軸方向の配置基準。' },
                            y_placement: { type: 'string', enum: ['center', 'front', 'back'], default: 'center', description: 'Y軸方向の配置基準。' }
                        }
                    }
                },
                {
                    name: 'create_polygon_prism',
                    description: '多角柱を作成します。',
                    inputSchema: {
                        type: 'object',
                        properties: {
                            num_sides: { type: 'number', default: 6, description: '多角形の辺の数。' },
                            radius: { type: 'number', default: 25, description: '外接円の半径 (mm)。' },
                            height: { type: 'number', default: 50, description: '高さ (mm)。' },
                            body_name: { type: 'string', description: '作成されるボディの名前（任意）。' },
                            plane: { type: 'string', enum: ['xy', 'xz', 'yz'], default: 'xy', description: '基準平面。' },
                            cx: { type: 'number', default: 0, description: '中心のX座標 (mm)。' },
                            cy: { type: 'number', default: 0, description: '中心のY座標 (mm)。' },
                            cz: { type: 'number', default: 0, description: '中心のZ座標 (mm)。' },
                            z_placement: { type: 'string', enum: ['center', 'bottom', 'top'], default: 'center', description: 'Z軸方向の配置基準。' },
                            x_placement: { type: 'string', enum: ['center', 'left', 'right'], default: 'center', description: 'X軸方向の配置基準。' },
                            y_placement: { type: 'string', enum: ['center', 'front', 'back'], default: 'center', description: 'Y軸方向の配置基準。' },
                            taper_angle: { type: 'number', default: 0, description: 'テーパー角度（度）。' },
                            taper_direction: { type: 'string', enum: ['inward', 'outward'], default: 'inward', description: 'テーパーの方向。' },
                            direction: { type: 'string', enum: ['positive', 'negative'], default: 'positive', description: '押し出し方向。' }
                        }
                    }
                },
                {
                    name: 'create_torus',
                    description: 'トーラス（ドーナツ形状）を作成します。',
                    inputSchema: {
                        type: 'object',
                        properties: {
                            major_radius: { type: 'number', default: 30, description: '大半径 (mm)。' },
                            minor_radius: { type: 'number', default: 10, description: '小半径 (mm)。' },
                            body_name: { type: 'string', description: '作成されるボディの名前（任意）。' },
                            plane: { type: 'string', enum: ['xy', 'xz', 'yz'], default: 'xy', description: '基準平面。' },
                            z_placement: { type: 'string', enum: ['center', 'bottom', 'top'], default: 'center', description: 'Z軸方向の配置基準。' },
                            x_placement: { type: 'string', enum: ['center', 'left', 'right'], default: 'center', description: 'X軸方向の配置基準。' },
                            y_placement: { type: 'string', enum: ['center', 'front', 'back'], default: 'center', description: 'Y軸方向の配置基準。' },
                            cx: { type: 'number', default: 0, description: '中心のX座標 (mm)。' },
                            cy: { type: 'number', default: 0, description: '中心のY座標 (mm)。' },
                            cz: { type: 'number', default: 0, description: '中心のZ座標 (mm)。' }
                        }
                    }
                },
                {
                    name: 'create_half_torus',
                    description: '半分のトーラス（半ドーナツ形状）を作成します。',
                    inputSchema: {
                        type: 'object',
                        properties: {
                            major_radius: { type: 'number', default: 30, description: '大半径 (mm)。' },
                            minor_radius: { type: 'number', default: 10, description: '小半径 (mm)。' },
                            body_name: { type: 'string', description: '作成されるボディの名前（任意）。' },
                            plane: { type: 'string', enum: ['xy', 'xz', 'yz'], default: 'xy', description: '基準平面。' },
                            orientation: { type: 'string', enum: ['back', 'front', 'left', 'right'], default: 'back', description: 'ハーフトーラスの開口部の向き。' },
                            plane_rotation_angle: { type: 'number', default: 0, description: '基準平面上での回転角度（度）。' },
                            opening_extrude_distance: { type: 'number', default: 0, description: '開口部の押し出し距離 (mm)。' },
                            z_placement: { type: 'string', enum: ['center', 'bottom', 'top'], default: 'center', description: 'Z軸方向の配置基準。' },
                            x_placement: { type: 'string', enum: ['center', 'left', 'right'], default: 'center', description: 'X軸方向の配置基準。' },
                            y_placement: { type: 'string', enum: ['center', 'front', 'back'], default: 'center', description: 'Y軸方向の配置基準。' },
                            cx: { type: 'number', default: 0, description: '中心のX座標 (mm)。' },
                            cy: { type: 'number', default: 0, description: '中心のY座標 (mm)。' },
                            cz: { type: 'number', default: 0, description: '中心のZ座標 (mm)。' }
                        }
                    }
                },
                {
                    name: 'create_pipe',
                    description: '指定した2点間にパイプを作成します。',
                    inputSchema: {
                        type: 'object',
                        properties: {
                            x1: { type: 'number', default: 0, description: '始点のX座標 (mm)。' },
                            y1: { type: 'number', default: 0, description: '始点のY座標 (mm)。' },
                            z1: { type: 'number', default: 0, description: '始点のZ座標 (mm)。' },
                            x2: { type: 'number', default: 50, description: '終点のX座標 (mm)。' },
                            y2: { type: 'number', default: 0, description: '終点のY座標 (mm)。' },
                            z2: { type: 'number', default: 50, description: '終点のZ座標 (mm)。' },
                            radius: { type: 'number', default: 5, description: 'パイプの半径 (mm)。' },
                            body_name: { type: 'string', description: '作成されるボディの名前（任意）。' }
                        }
                    }
                },
                {
                    name: 'create_polygon_sweep',
                    description: '多角形プロファイルを円形パスでスイープして3D形状を作成します。',
                    inputSchema: {
                        type: 'object',
                        properties: {
                            profile_sides: { type: 'number', default: 6, description: 'プロファイル多角形の辺数。' },
                            profile_radius: { type: 'number', default: 10, description: 'プロファイル多角形の外接円半径 (mm)。' },
                            path_radius: { type: 'number', default: 30, description: 'スイープパスの円の半径 (mm)。' },
                            sweep_angle: { type: 'number', enum: [360], default: 360, description: 'スイープ角度（360度固定）。' },
                            twist_rotations: { type: 'number', enum: [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10], default: 0, description: 'ねじりの回転数（0-10）。' },
                            body_name: { type: 'string', description: '作成されるボディの名前（任意）。' },
                            plane: { type: 'string', enum: ['xy', 'xz', 'yz'], default: 'xy', description: '基準平面。' },
                            cx: { type: 'number', default: 0, description: '中心のX座標 (mm)。' },
                            cy: { type: 'number', default: 0, description: '中心のY座標 (mm)。' },
                            cz: { type: 'number', default: 0, description: '中心のZ座標 (mm)。' },
                            z_placement: { type: 'string', enum: ['center', 'bottom', 'top'], default: 'center', description: 'Z軸方向の配置基準。' },
                            x_placement: { type: 'string', enum: ['center', 'left', 'right'], default: 'center', description: 'X軸方向の配置基準。' },
                            y_placement: { type: 'string', enum: ['center', 'front', 'back'], default: 'center', description: 'Y軸方向の配置基準。' }
                        }
                    }
                },
                // === Pattern/Copy Tools ===
                {
                    name: 'copy_body_symmetric',
                    description: 'ボディを平面に対して対称にコピー（ミラー）します。',
                    inputSchema: {
                        type: 'object',
                        properties: {
                            source_body_name: { type: 'string', description: 'コピー元のボディ名。' },
                            new_body_name: { type: 'string', description: '作成される新しいボディ名。' },
                            plane: { type: 'string', enum: ['xy', 'xz', 'yz'], default: 'xy', description: 'ミラー平面。' }
                        },
                        required: ['source_body_name', 'new_body_name']
                    }
                },
                {
                    name: 'create_circular_pattern',
                    description: 'ボディの円形状パターンを作成します。',
                    inputSchema: {
                        type: 'object',
                        properties: {
                            source_body_name: { type: 'string', description: 'パターン化する元のボディ名。' },
                            axis: { type: 'string', enum: ['x', 'y', 'z'], default: 'z', description: '回転軸。' },
                            quantity: { type: 'number', default: 4, description: '作成するインスタンスの合計数。' },
                            angle: { type: 'number', default: 360.0, description: 'パターンの合計角度（度）。' },
                            new_body_base_name: { type: 'string', description: '新しいボディのベース名（任意）。' }
                        },
                        required: ['source_body_name']
                    }
                },
                {
                    name: 'create_rectangular_pattern',
                    description: 'ボディの矩形状パターンを作成します。',
                    inputSchema: {
                        type: 'object',
                        properties: {
                            source_body_name: { type: 'string', description: 'パターン化する元のボディ名。' },
                            distance_type: { type: 'string', enum: ['spacing', 'extent'], default: 'spacing', description: '距離のタイプ。' },
                            quantity_one: { type: 'number', default: 2, description: '1方向目の個数。' },
                            distance_one: { type: 'number', default: 10, description: '1方向目の距離 (mm)。' },
                            direction_one_axis: { type: 'string', enum: ['x', 'y', 'z'], default: 'x', description: '1方向目の軸。' },
                            quantity_two: { type: 'number', default: 1, description: '2方向目の個数。' },
                            distance_two: { type: 'number', default: 10, description: '2方向目の距離 (mm)。' },
                            direction_two_axis: { type: 'string', enum: ['x', 'y', 'z'], default: 'y', description: '2方向目の軸。' },
                            new_body_base_name: { type: 'string', description: '新しいボディのベース名（任意）。' }
                        },
                        required: ['source_body_name']
                    }
                },
                // === Modification Tools ===
				{
					name: 'add_fillet',
					description: '指定したボディの特定のエッジにフィレットを追加します。',
					inputSchema: {
						type: 'object',
						properties: {
							body_name: { type: 'string', description: 'フィレットを適用するボディの名前。' },
							radius: { type: 'number', default: 1, description: 'フィレット半径 (mm)。' },
							edge_indices: {
								type: 'array',
								description: 'フィレットを適用するエッジのインデックス番号のリスト。get_edges_infoで確認できます。省略するとボディの全ての外周エッジが対象になります。',
								items: { type: 'integer' }
							}
						},
						required: ['body_name', 'radius']
					}
				},
				{
					name: 'add_chamfer',
					description: '指定したボディの特定のエッジに面取りを追加します。',
					inputSchema: {
						type: 'object',
						properties: {
							body_name: { type: 'string', description: '面取りを適用するボディの名前。' },
							distance: { type: 'number', default: 1, description: '面取り距離 (mm)。' },
							edge_indices: {
								type: 'array',
								description: '面取りを適用するエッジのインデックス番号のリスト。get_edges_infoで確認できます。省略するとボディの全ての外周エッジが対象になります。',
								items: { type: 'integer' }
							}
						},
						required: ['body_name', 'distance']
					}
				},
				{
                    name: 'combine_selection',
                    description: '選択した複数のボディを結合（ブール演算）します。最初の選択がターゲットになります。',
                    inputSchema: {
                        type: 'object',
                        properties: {
                            operation: { type: 'string', enum: ['join', 'cut', 'intersect'], description: '実行するブール演算。' },
                            new_body_name: { type: 'string', description: '結果のボディ名（任意）。' }
                        },
                        required: ['operation']
                    }
                },
                {
                    name: 'combine_selection_all',
                    description: '選択したすべてのボディを結合（ブール演算）します。',
                    inputSchema: {
                        type: 'object',
                        properties: {
                            operation: { type: 'string', enum: ['join', 'cut', 'intersect'], default: 'join', description: '実行するブール演算。' },
                            new_body_name: { type: 'string', description: '結果のボディ名（任意）。' }
                        }
                    }
                },
                {
                    name: 'combine_by_name',
                    description: '名前で指定した2つのボディを結合（ブール演算）します。',
                    inputSchema: {
                        type: 'object',
                        properties: {
                            target_body: { type: 'string', description: 'ターゲットボディの名前。' },
                            tool_body: { type: 'string', description: 'ツールボディの名前。' },
                            operation: { type: 'string', enum: ['join', 'cut', 'intersect'], description: '実行するブール演算。' },
                            new_body_name: { type: 'string', description: '結果のボディ名（任意）。' }
                        },
                        required: ['target_body', 'tool_body', 'operation']
                    }
                },
                // === Transformation & Visibility Tools ===
                { name: 'hide_body', description: '名前でボディを非表示にします。', inputSchema: { type: 'object', properties: { body_name: { type: 'string', description: '非表示にするボディ名。' } }, required: ['body_name'] } },
                { name: 'show_body', description: '名前で非表示のボディを表示します。', inputSchema: { type: 'object', properties: { body_name: { type: 'string', description: '表示するボディ名。' } }, required: ['body_name'] } },
                { name: 'move_by_name', description: '名前でボディを移動します。', inputSchema: { type: 'object', properties: { body_name: { type: 'string', description: '移動するボディ名。' }, x_dist: { type: 'number', default: 0, description: 'X方向の移動距離 (mm)。' }, y_dist: { type: 'number', default: 0, description: 'Y方向の移動距離 (mm)。' }, z_dist: { type: 'number', default: 0, description: 'Z方向の移動距離 (mm)。' } }, required: ['body_name'] } },
                { name: 'rotate_by_name', description: '名前でボディを回転します。', inputSchema: { type: 'object', properties: { body_name: { type: 'string', description: '回転するボディ名。' }, axis: { type: 'string', enum: ['x', 'y', 'z'], default: 'z', description: '回転軸。' }, angle: { type: 'number', default: 90, description: '回転角度（度数）。' }, cx: { type: 'number', default: 0, description: '回転中心のX座標 (mm)。' }, cy: { type: 'number', default: 0, description: '回転中心のY座標 (mm)。' }, cz: { type: 'number', default: 0, description: '回転中心のZ座標 (mm)。' } }, required: ['body_name'] } },
                
                // === Selection Tools ===
                { name: 'select_body', description: '名前でボディを1つ選択します。', inputSchema: { type: 'object', properties: { body_name: { type: 'string', description: '選択するボディ名。' } }, required: ['body_name'] } },
                {
                    name: 'select_bodies',
                    description: '名前で指定した2つのボディを選択します。',
                    inputSchema: {
                        type: 'object',
                        properties: {
                            body_name1: { type: 'string', description: '選択する1つ目のボディ名。' },
                            body_name2: { type: 'string', description: '選択する2つ目のボディ名。' }
                        },
                        required: ['body_name1', 'body_name2']
                    }
                },
                { name: 'select_all_bodies', description: 'ドキュメント内のすべてのボディを選択します。', inputSchema: { type: 'object', properties: {} } },
                
                // === Body Information Tools ===
                {
                    name: 'get_bounding_box',
                    description: '指定したボディのバウンディングボックス情報を取得します。',
                    inputSchema: {
                        type: 'object',
                        properties: {
                            body_name: { 
                                type: 'string', 
                                description: '情報を取得するボディの名前。' 
                            }
                        },
                        required: ['body_name']
                    }
                },
                {
                    name: 'get_body_center',
                    description: '指定したボディの中心点情報（幾何学的中心、重心、バウンディング中心）を取得します。',
                    inputSchema: {
                        type: 'object',
                        properties: {
                            body_name: { 
                                type: 'string', 
                                description: '情報を取得するボディの名前。' 
                            }
                        },
                        required: ['body_name']
                    }
                },
                {
                    name: 'get_body_dimensions',
                    description: '指定したボディの詳細寸法情報（長さ、幅、高さ、体積、表面積）を取得します。',
                    inputSchema: {
                        type: 'object',
                        properties: {
                            body_name: { 
                                type: 'string', 
                                description: '情報を取得するボディの名前。' 
                            }
                        },
                        required: ['body_name']
                    }
                },
                {
                    name: 'get_faces_info',
                    description: '指定したボディの面情報（タイプ、面積、法線、中心点など）を取得します。',
                    inputSchema: {
                        type: 'object',
                        properties: {
                            body_name: { 
                                type: 'string', 
                                description: '情報を取得するボディの名前。' 
                            }
                        },
                        required: ['body_name']
                    }
                },
                {
                    name: 'get_edges_info',
                    description: '指定したボディのエッジ情報（タイプ、長さ、方向、始点・終点など）を取得します。',
                    inputSchema: {
                        type: 'object',
                        properties: {
                            body_name: { 
                                type: 'string', 
                                description: '情報を取得するボディの名前。' 
                            }
                        },
                        required: ['body_name']
                    }
                },
                {
                    name: 'get_mass_properties',
                    description: '指定したボディの質量特性（体積、質量、重心、慣性モーメント）を取得します。',
                    inputSchema: {
                        type: 'object',
                        properties: {
                            body_name: { 
                                type: 'string', 
                                description: '情報を取得するボディの名前。' 
                            },
                            material_density: { 
                                type: 'number', 
                                default: 1.0, 
                                description: '材料密度 (g/cm³)。質量計算に使用されます。' 
                            }
                        },
                        required: ['body_name']
                    }
                },
                {
                    name: 'get_body_relationships',
                    description: '2つのボディ間の位置関係（距離、干渉、相対位置など）を取得します。',
                    inputSchema: {
                        type: 'object',
                        properties: {
                            body_name: { 
                                type: 'string', 
                                description: '基準となるボディの名前。' 
                            },
                            other_body_name: { 
                                type: 'string', 
                                description: '比較対象のボディの名前。' 
                            }
                        },
                        required: ['body_name', 'other_body_name']
                    }
                },
                {
                    name: 'measure_distance',
                    description: '2つのボディ間の距離を測定します（重心間距離とバウンディングボックス間クリアランス）。',
                    inputSchema: {
                        type: 'object',
                        properties: {
                            body_name1: { 
                                type: 'string', 
                                description: '距離測定する1つ目のボディの名前。' 
                            },
                            body_name2: { 
                                type: 'string', 
                                description: '距離測定する2つ目のボディの名前。' 
                            }
                        },
                        required: ['body_name1', 'body_name2']
                    }
                },
                
                // === Utility Tools ===
                { 
                    name: 'delete_all_features', 
                    description: 'タイムライン上のすべてのフィーチャを削除し、デザインを初期化します。', 
                    inputSchema: { type: 'object', properties: {} } 
                }, 
                { name: 'debug_coordinate_info', description: '座標系や単位に関するデバッグ情報を出力します。', inputSchema: { type: 'object', properties: { show_details: { type: 'boolean', default: true, description: '詳細情報を表示するかどうか。' } } } }
            ];
            logDebug(`Returning ${tools.length} tools (including body info functions)`);
            return { tools };
        });

        this.server.setRequestHandler(CallToolRequestSchema, async (request) => {
            const { name, arguments: args } = request.params;
            logDebug(`CallToolRequest received for tool: ${name}`, args);
            try {
                await this.clearResponseFile();
                await this.executeFusionCommand(name, args || {});
                logDebug(`Command '${name}' sent, waiting for response...`);
                const responseContent = await this.waitForResponseFileUpdate();
                let responseJson;
                try {
                    responseJson = JSON.parse(responseContent);
                } catch (parseError) {
                    logDebug('Failed to parse JSON response:', responseContent);
                    throw new McpError(ErrorCode.InternalError, 'Received malformed response from Fusion 360.');
                }
                if (responseJson.status === 'error') {
                    logDebug(`Received error from Fusion 360: ${responseJson.message}`);
                    const errorMessage = `Fusion 360 Error for '${name}': ${responseJson.message}\n\nTraceback:\n${responseJson.traceback || 'N/A'}`;
                    throw new McpError(ErrorCode.InternalError, errorMessage);
                }
                logDebug(`Successfully executed '${name}'. Result:`, responseJson.result);
                let responseText = `Fusion 360 command '${name}' executed successfully.`;
                if (responseJson.result) {
                    const resultString = typeof responseJson.result === 'object' ? JSON.stringify(responseJson.result, null, 2) : responseJson.result;
                    responseText += `\n\n**Result:**\n\`\`\`\n${resultString}\n\`\`\``;
                }
                return { content: [{ type: 'text', text: responseText }] };
            } catch (error) {
                logDebug(`Error executing tool '${name}':`, error);
                if (error instanceof McpError) { throw error; }
                throw new McpError(ErrorCode.InternalError, `Failed to execute command '${name}': ${error.message}`);
            }
        });
        logDebug('Tool handlers set up successfully.');
    }

    async executeFusionCommand(command, parameters) {
        logDebug(`Executing Fusion command: ${command}`, parameters);
        const commandData = {
            command: command,
            parameters: parameters, // パラメータの前処理はここでは省略
            timestamp: new Date().toISOString(),
        };
        const maxRetries = 3;
        let lastError = null;
        for (let attempt = 1; attempt <= maxRetries; attempt++) {
            try {
                const tempPath = `${commandFilePath}.tmp.${Date.now()}.${process.pid}`;
                await fs.writeFile(tempPath, JSON.stringify(commandData, null, 2), 'utf8');
                await fs.rename(tempPath, commandFilePath);
                logDebug('Command file written successfully');
                return;
            } catch (error) {
                lastError = error;
                logDebug(`File operation attempt ${attempt} failed:`, error.message);
                if (attempt < maxRetries) await new Promise(resolve => setTimeout(resolve, Math.pow(2, attempt) * 100));
            }
        }
        throw new Error(`Failed to write command file after ${maxRetries} attempts: ${lastError.message}`);
    }
    
    async run() {
        logDebug('Starting server connection...');
        const transport = new StdioServerTransport();
        this.server.onerror = (error) => { logDebug('Server error occurred:', error); };
        await this.server.connect(transport);
        logDebug('Server connected successfully via stdio transport.');
    }
}

async function main() {
    logDebug('Starting Fusion MCP Server...');
    try {
        const server = new JapaneseFusion360MCPServer();
        await server.run();
        logDebug('Server is now running and ready for connections.');
    } catch (error) {
        logDebug('Failed to start server:', error);
        process.exit(1);
    }
}

process.on('SIGINT', () => { logDebug('Received SIGINT, shutting down...'); process.exit(0); });
process.on('SIGTERM', () => { logDebug('Received SIGTERM, shutting down...'); process.exit(0); });
process.on('uncaughtException', (error) => { logDebug('Uncaught exception:', error); process.exit(1); });
process.on('unhandledRejection', (reason) => { logDebug('Unhandled rejection:', reason); process.exit(1); });

main();