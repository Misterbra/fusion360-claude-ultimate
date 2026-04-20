#!/usr/bin/env node
// Fusion 360 MCP Server v1.0
// Bridges Claude Desktop with Autodesk Fusion 360 via file-based JSON communication.

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
    console.error(`[FUSION-MCP] ${new Date().toISOString()} - ${message}`, ...args);
};

const commandFilePath = path.join(os.homedir(), 'Documents', 'fusion_command.txt');
const responseFilePath = path.join(os.homedir(), 'Documents', 'fusion_response.txt');

class Fusion360MCPServer {
    constructor() {
        logDebug('Initializing Fusion 360 MCP Server...');
        this.server = new Server(
            { name: 'fusion-mcp-server', version: '1.0.0' },
            { capabilities: { tools: {} } }
        );
        this.setupToolHandlers();
        logDebug('Server constructor finished.');
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
                // File doesn't exist yet, retry on next poll
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
        logDebug('Setting up tool handlers...');

        this.server.setRequestHandler(ListToolsRequestSchema, async () => {
            logDebug('ListToolsRequest received.');
            const tools = [
                // === Macro Tool ===
                {
                    name: 'execute_macro',
                    description: 'Execute multiple modeling commands in sequence.',
                    inputSchema: {
                        type: 'object',
                        properties: {
                            commands: {
                                type: 'array',
                                description: 'Array of command objects to execute.',
                                items: {
                                    type: 'object',
                                    properties: {
                                        tool_name: { type: 'string', description: 'Tool name to call.' },
                                        arguments: { type: 'object', description: 'Arguments for the tool.' }
                                    },
                                    required: ['tool_name']
                                }
                            }
                        },
                        required: ['commands']
                    }
                },

                // === Shape Creation Tools ===
                {
                    name: 'create_cube',
                    description: 'Create a cube. Placement options: bottom/center/top.',
                    inputSchema: {
                        type: 'object',
                        properties: {
                            size: { type: 'number', default: 50, description: 'Side length (mm).' },
                            body_name: { type: 'string', description: 'Body name (optional).' },
                            plane: { type: 'string', enum: ['xy', 'xz', 'yz'], default: 'xy', description: 'Base plane.' },
                            cx: { type: 'number', default: 0, description: 'Center X (mm).' },
                            cy: { type: 'number', default: 0, description: 'Center Y (mm).' },
                            cz: { type: 'number', default: 0, description: 'Center Z (mm).' },
                            z_placement: { type: 'string', enum: ['center', 'bottom', 'top'], default: 'center', description: 'Z placement.' },
                            x_placement: { type: 'string', enum: ['center', 'left', 'right'], default: 'center', description: 'X placement.' },
                            y_placement: { type: 'string', enum: ['center', 'front', 'back'], default: 'center', description: 'Y placement.' },
                            taper_angle: { type: 'number', default: 0, description: 'Taper angle (degrees).' },
                            taper_direction: { type: 'string', enum: ['inward', 'outward'], default: 'inward', description: 'Taper direction.' },
                            direction: { type: 'string', enum: ['positive', 'negative'], default: 'positive', description: 'Extrusion direction.' }
                        }
                    }
                },
                {
                    name: 'create_cylinder',
                    description: 'Create a cylinder.',
                    inputSchema: {
                        type: 'object',
                        properties: {
                            radius: { type: 'number', default: 25, description: 'Radius (mm).' },
                            height: { type: 'number', default: 50, description: 'Height (mm).' },
                            body_name: { type: 'string', description: 'Body name (optional).' },
                            plane: { type: 'string', enum: ['xy', 'xz', 'yz'], default: 'xy', description: 'Base plane.' },
                            cx: { type: 'number', default: 0, description: 'Center X (mm).' },
                            cy: { type: 'number', default: 0, description: 'Center Y (mm).' },
                            cz: { type: 'number', default: 0, description: 'Center Z (mm).' },
                            z_placement: { type: 'string', enum: ['center', 'bottom', 'top'], default: 'center', description: 'Z placement.' },
                            x_placement: { type: 'string', enum: ['center', 'left', 'right'], default: 'center', description: 'X placement.' },
                            y_placement: { type: 'string', enum: ['center', 'front', 'back'], default: 'center', description: 'Y placement.' },
                            taper_angle: { type: 'number', default: 0, description: 'Taper angle (degrees).' },
                            taper_direction: { type: 'string', enum: ['inward', 'outward'], default: 'inward', description: 'Taper direction.' },
                            direction: { type: 'string', enum: ['positive', 'negative'], default: 'positive', description: 'Extrusion direction.' }
                        }
                    }
                },
                {
                    name: 'create_box',
                    description: 'Create a rectangular box.',
                    inputSchema: {
                        type: 'object',
                        properties: {
                            width: { type: 'number', default: 50, description: 'Width X (mm).' },
                            depth: { type: 'number', default: 30, description: 'Depth Y (mm).' },
                            height: { type: 'number', default: 20, description: 'Height Z (mm).' },
                            body_name: { type: 'string', description: 'Body name (optional).' },
                            plane: { type: 'string', enum: ['xy', 'xz', 'yz'], default: 'xy', description: 'Base plane.' },
                            cx: { type: 'number', default: 0, description: 'Center X (mm).' },
                            cy: { type: 'number', default: 0, description: 'Center Y (mm).' },
                            cz: { type: 'number', default: 0, description: 'Center Z (mm).' },
                            z_placement: { type: 'string', enum: ['center', 'bottom', 'top'], default: 'center', description: 'Z placement.' },
                            x_placement: { type: 'string', enum: ['center', 'left', 'right'], default: 'center', description: 'X placement.' },
                            y_placement: { type: 'string', enum: ['center', 'front', 'back'], default: 'center', description: 'Y placement.' },
                            taper_angle: { type: 'number', default: 0, description: 'Taper angle (degrees).' },
                            taper_direction: { type: 'string', enum: ['inward', 'outward'], default: 'inward', description: 'Taper direction.' },
                            direction: { type: 'string', enum: ['positive', 'negative'], default: 'positive', description: 'Extrusion direction.' }
                        }
                    }
                },
                {
                    name: 'create_sphere',
                    description: 'Create a sphere.',
                    inputSchema: { type: 'object', properties: {
                        radius: { type: 'number', default: 25, description: 'Radius (mm).' },
                        body_name: { type: 'string', description: 'Body name (optional).' },
                        cx: { type: 'number', default: 0, description: 'Center X (mm).' },
                        cy: { type: 'number', default: 0, description: 'Center Y (mm).' },
                        cz: { type: 'number', default: 0, description: 'Center Z (mm).' }
                    }}
                },
                {
                    name: 'create_hemisphere',
                    description: 'Create a hemisphere.',
                    inputSchema: { type: 'object', properties: {
                        radius: { type: 'number', default: 25, description: 'Radius (mm).' },
                        body_name: { type: 'string', description: 'Body name (optional).' },
                        plane: { type: 'string', enum: ['xy', 'xz', 'yz'], default: 'xy', description: 'Base plane.' },
                        cx: { type: 'number', default: 0, description: 'Center X (mm).' },
                        cy: { type: 'number', default: 0, description: 'Center Y (mm).' },
                        cz: { type: 'number', default: 0, description: 'Center Z (mm).' },
                        orientation: { type: 'string', enum: ['positive', 'negative'], default: 'positive', description: 'Hemisphere orientation.' },
                        z_placement: { type: 'string', enum: ['bottom', 'center', 'top'], default: 'bottom', description: 'Z placement.' },
                        x_placement: { type: 'string', enum: ['center', 'left', 'right'], default: 'center', description: 'X placement.' },
                        y_placement: { type: 'string', enum: ['center', 'front', 'back'], default: 'center', description: 'Y placement.' }
                    }}
                },
                {
                    name: 'create_cone',
                    description: 'Create a cone.',
                    inputSchema: { type: 'object', properties: {
                        radius: { type: 'number', default: 25, description: 'Base radius (mm).' },
                        height: { type: 'number', default: 50, description: 'Height (mm).' },
                        body_name: { type: 'string', description: 'Body name (optional).' },
                        plane: { type: 'string', enum: ['xy', 'xz', 'yz'], default: 'xy', description: 'Base plane.' },
                        cx: { type: 'number', default: 0, description: 'Center X (mm).' },
                        cy: { type: 'number', default: 0, description: 'Center Y (mm).' },
                        cz: { type: 'number', default: 0, description: 'Center Z (mm).' },
                        z_placement: { type: 'string', enum: ['center', 'bottom', 'top'], default: 'center', description: 'Z placement.' },
                        x_placement: { type: 'string', enum: ['center', 'left', 'right'], default: 'center', description: 'X placement.' },
                        y_placement: { type: 'string', enum: ['center', 'front', 'back'], default: 'center', description: 'Y placement.' }
                    }}
                },
                {
                    name: 'create_polygon_prism',
                    description: 'Create a polygon prism (N-sided).',
                    inputSchema: { type: 'object', properties: {
                        num_sides: { type: 'integer', default: 6, description: 'Number of sides.' },
                        radius: { type: 'number', default: 25, description: 'Circumscribed radius (mm).' },
                        height: { type: 'number', default: 50, description: 'Height (mm).' },
                        body_name: { type: 'string', description: 'Body name (optional).' },
                        plane: { type: 'string', enum: ['xy', 'xz', 'yz'], default: 'xy', description: 'Base plane.' },
                        cx: { type: 'number', default: 0, description: 'Center X (mm).' },
                        cy: { type: 'number', default: 0, description: 'Center Y (mm).' },
                        cz: { type: 'number', default: 0, description: 'Center Z (mm).' },
                        z_placement: { type: 'string', enum: ['center', 'bottom', 'top'], default: 'center', description: 'Z placement.' },
                        x_placement: { type: 'string', enum: ['center', 'left', 'right'], default: 'center', description: 'X placement.' },
                        y_placement: { type: 'string', enum: ['center', 'front', 'back'], default: 'center', description: 'Y placement.' },
                        taper_angle: { type: 'number', default: 0, description: 'Taper angle (degrees).' },
                        taper_direction: { type: 'string', enum: ['inward', 'outward'], default: 'inward', description: 'Taper direction.' },
                        direction: { type: 'string', enum: ['positive', 'negative'], default: 'positive', description: 'Extrusion direction.' }
                    }}
                },
                {
                    name: 'create_torus',
                    description: 'Create a torus (donut shape).',
                    inputSchema: { type: 'object', properties: {
                        major_radius: { type: 'number', default: 30, description: 'Major radius (mm).' },
                        minor_radius: { type: 'number', default: 10, description: 'Minor radius (mm).' },
                        body_name: { type: 'string', description: 'Body name (optional).' },
                        plane: { type: 'string', enum: ['xy', 'xz', 'yz'], default: 'xy', description: 'Base plane.' },
                        z_placement: { type: 'string', enum: ['center', 'bottom', 'top'], default: 'center', description: 'Z placement.' },
                        x_placement: { type: 'string', enum: ['center', 'left', 'right'], default: 'center', description: 'X placement.' },
                        y_placement: { type: 'string', enum: ['center', 'front', 'back'], default: 'center', description: 'Y placement.' },
                        cx: { type: 'number', default: 0, description: 'Center X (mm).' },
                        cy: { type: 'number', default: 0, description: 'Center Y (mm).' },
                        cz: { type: 'number', default: 0, description: 'Center Z (mm).' }
                    }}
                },
                {
                    name: 'create_half_torus',
                    description: 'Create a half torus.',
                    inputSchema: { type: 'object', properties: {
                        major_radius: { type: 'number', default: 30, description: 'Major radius (mm).' },
                        minor_radius: { type: 'number', default: 10, description: 'Minor radius (mm).' },
                        body_name: { type: 'string', description: 'Body name (optional).' },
                        plane: { type: 'string', enum: ['xy', 'xz', 'yz'], default: 'xy', description: 'Base plane.' },
                        orientation: { type: 'string', enum: ['back', 'front', 'left', 'right'], default: 'back', description: 'Opening orientation.' },
                        plane_rotation_angle: { type: 'number', default: 0, description: 'Rotation angle on the plane (degrees).' },
                        opening_extrude_distance: { type: 'number', default: 0, description: 'Opening extrusion distance (mm).' },
                        z_placement: { type: 'string', enum: ['center', 'bottom', 'top'], default: 'center', description: 'Z placement.' },
                        x_placement: { type: 'string', enum: ['center', 'left', 'right'], default: 'center', description: 'X placement.' },
                        y_placement: { type: 'string', enum: ['center', 'front', 'back'], default: 'center', description: 'Y placement.' },
                        cx: { type: 'number', default: 0, description: 'Center X (mm).' },
                        cy: { type: 'number', default: 0, description: 'Center Y (mm).' },
                        cz: { type: 'number', default: 0, description: 'Center Z (mm).' }
                    }}
                },
                {
                    name: 'create_pipe',
                    description: 'Create a pipe between two 3D points.',
                    inputSchema: { type: 'object', properties: {
                        x1: { type: 'number', default: 0, description: 'Start X (mm).' },
                        y1: { type: 'number', default: 0, description: 'Start Y (mm).' },
                        z1: { type: 'number', default: 0, description: 'Start Z (mm).' },
                        x2: { type: 'number', default: 50, description: 'End X (mm).' },
                        y2: { type: 'number', default: 0, description: 'End Y (mm).' },
                        z2: { type: 'number', default: 50, description: 'End Z (mm).' },
                        radius: { type: 'number', default: 5, description: 'Pipe radius (mm).' },
                        body_name: { type: 'string', description: 'Body name (optional).' }
                    }}
                },
                {
                    name: 'create_polygon_sweep',
                    description: 'Sweep a polygon profile along a circular path to create a 3D shape.',
                    inputSchema: { type: 'object', properties: {
                        profile_sides: { type: 'integer', default: 6, description: 'Profile polygon sides.' },
                        profile_radius: { type: 'number', default: 10, description: 'Profile circumscribed radius (mm).' },
                        path_radius: { type: 'number', default: 30, description: 'Sweep path circle radius (mm).' },
                        twist_rotations: { type: 'integer', default: 0, description: 'Twist rotations (0-10).' },
                        body_name: { type: 'string', description: 'Body name (optional).' },
                        plane: { type: 'string', enum: ['xy', 'xz', 'yz'], default: 'xy', description: 'Base plane.' },
                        cx: { type: 'number', default: 0, description: 'Center X (mm).' },
                        cy: { type: 'number', default: 0, description: 'Center Y (mm).' },
                        cz: { type: 'number', default: 0, description: 'Center Z (mm).' },
                        z_placement: { type: 'string', enum: ['center', 'bottom', 'top'], default: 'center', description: 'Z placement.' },
                        x_placement: { type: 'string', enum: ['center', 'left', 'right'], default: 'center', description: 'X placement.' },
                        y_placement: { type: 'string', enum: ['center', 'front', 'back'], default: 'center', description: 'Y placement.' }
                    }}
                },

                // === Pattern/Copy Tools ===
                { name: 'copy_body_symmetric', description: 'Mirror-copy a body across a plane.', inputSchema: { type: 'object', properties: { source_body_name: { type: 'string', description: 'Source body name.' }, new_body_name: { type: 'string', description: 'New body name.' }, plane: { type: 'string', enum: ['xy', 'xz', 'yz'], default: 'xy', description: 'Mirror plane.' } }, required: ['source_body_name', 'new_body_name'] } },
                { name: 'copy_body', description: 'Duplicate a body with optional offset.', inputSchema: { type: 'object', properties: { body_name: { type: 'string', description: 'Body to copy.' }, new_body_name: { type: 'string', description: 'Name for the copy.' }, x_offset: { type: 'number', default: 0, description: 'X offset (mm).' }, y_offset: { type: 'number', default: 0, description: 'Y offset (mm).' }, z_offset: { type: 'number', default: 0, description: 'Z offset (mm).' } }, required: ['body_name'] } },
                {
                    name: 'create_circular_pattern',
                    description: 'Create a circular array of a body.',
                    inputSchema: { type: 'object', properties: {
                        source_body_name: { type: 'string', description: 'Source body name.' },
                        axis: { type: 'string', enum: ['x', 'y', 'z'], default: 'z', description: 'Rotation axis.' },
                        quantity: { type: 'integer', default: 4, description: 'Total instance count.' },
                        angle: { type: 'number', default: 360.0, description: 'Total angle (degrees).' },
                        new_body_base_name: { type: 'string', description: 'Base name for new bodies (optional).' }
                    }, required: ['source_body_name'] }
                },
                {
                    name: 'create_rectangular_pattern',
                    description: 'Create a rectangular grid array of a body.',
                    inputSchema: { type: 'object', properties: {
                        source_body_name: { type: 'string', description: 'Source body name.' },
                        distance_type: { type: 'string', enum: ['spacing', 'extent'], default: 'spacing', description: 'Distance type.' },
                        quantity_one: { type: 'integer', default: 2, description: 'Count in direction 1.' },
                        distance_one: { type: 'number', default: 10, description: 'Distance in direction 1 (mm).' },
                        direction_one_axis: { type: 'string', enum: ['x', 'y', 'z'], default: 'x', description: 'Direction 1 axis.' },
                        quantity_two: { type: 'integer', default: 1, description: 'Count in direction 2.' },
                        distance_two: { type: 'number', default: 10, description: 'Distance in direction 2 (mm).' },
                        direction_two_axis: { type: 'string', enum: ['x', 'y', 'z'], default: 'y', description: 'Direction 2 axis.' },
                        new_body_base_name: { type: 'string', description: 'Base name for new bodies (optional).' }
                    }, required: ['source_body_name'] }
                },

                // === Geometry Operations (LOT 1) ===
                {
                    name: 'shell_body', description: 'Hollow out a body, leaving walls of specified thickness.',
                    inputSchema: { type: 'object', properties: {
                        body_name: { type: 'string', description: 'Body to shell.' },
                        thickness: { type: 'number', default: 2, description: 'Wall thickness (mm).' },
                        face_indices: { type: 'array', items: { type: 'integer' }, description: 'Face indices to remove (0-based).' }
                    }, required: ['body_name'] }
                },
                {
                    name: 'create_hole', description: 'Create a hole on a body face (simple or through-all).',
                    inputSchema: { type: 'object', properties: {
                        body_name: { type: 'string', description: 'Target body.' },
                        face_index: { type: 'integer', default: 0, description: 'Face index (0-based).' },
                        x: { type: 'number', default: 0, description: 'Hole center X on face (mm).' },
                        y: { type: 'number', default: 0, description: 'Hole center Y on face (mm).' },
                        diameter: { type: 'number', default: 10, description: 'Hole diameter (mm).' },
                        depth: { type: 'number', default: 0, description: 'Hole depth (mm). 0 = through all.' },
                        hole_type: { type: 'string', enum: ['simple', 'through_all'], default: 'simple', description: 'Hole type.' }
                    }, required: ['body_name', 'diameter'] }
                },
                {
                    name: 'create_thread', description: 'Add thread to a cylindrical face.',
                    inputSchema: { type: 'object', properties: {
                        body_name: { type: 'string', description: 'Target body.' },
                        face_index: { type: 'integer', default: 0, description: 'Cylindrical face index (0-based).' },
                        thread_type: { type: 'string', default: 'ISO Metric profile', description: 'Thread type.' },
                        size: { type: 'string', default: 'M10', description: 'Thread size.' },
                        designation: { type: 'string', default: 'M10x1.5', description: 'Thread designation.' },
                        is_internal: { type: 'boolean', default: true, description: 'Internal (true) or external (false).' },
                        full_length: { type: 'boolean', default: true, description: 'Thread full length of face.' },
                        length: { type: 'number', default: 0, description: 'Thread length if not full (mm).' }
                    }, required: ['body_name'] }
                },
                { name: 'offset_face', description: 'Move faces inward/outward to thicken or thin walls.', inputSchema: { type: 'object', properties: { body_name: { type: 'string', description: 'Target body.' }, face_indices: { type: 'array', items: { type: 'integer' }, description: 'Face indices (0-based).' }, distance: { type: 'number', default: 1, description: 'Offset distance (mm). Positive=outward.' } }, required: ['body_name', 'face_indices', 'distance'] } },
                { name: 'split_body', description: 'Split a body with a construction plane.', inputSchema: { type: 'object', properties: { body_name: { type: 'string', description: 'Body to split.' }, plane: { type: 'string', enum: ['xy', 'xz', 'yz'], default: 'xy', description: 'Splitting plane.' }, offset: { type: 'number', default: 0, description: 'Plane offset (mm).' } }, required: ['body_name'] } },
                { name: 'scale_body', description: 'Scale a body uniformly or non-uniformly.', inputSchema: { type: 'object', properties: { body_name: { type: 'string', description: 'Body to scale.' }, scale_x: { type: 'number', default: 1, description: 'X scale factor.' }, scale_y: { type: 'number', default: 1, description: 'Y scale factor.' }, scale_z: { type: 'number', default: 1, description: 'Z scale factor.' }, cx: { type: 'number', default: 0, description: 'Scale center X (mm).' }, cy: { type: 'number', default: 0, description: 'Scale center Y (mm).' }, cz: { type: 'number', default: 0, description: 'Scale center Z (mm).' } }, required: ['body_name'] } },
                { name: 'draft_face', description: 'Add draft angle to faces for mold release.', inputSchema: { type: 'object', properties: { body_name: { type: 'string', description: 'Target body.' }, face_indices: { type: 'array', items: { type: 'integer' }, description: 'Face indices (0-based).' }, draft_angle: { type: 'number', default: 3, description: 'Draft angle (degrees).' }, pull_direction_axis: { type: 'string', enum: ['x', 'y', 'z'], default: 'z', description: 'Pull direction axis.' } }, required: ['body_name', 'face_indices'] } },

                // === Modification Tools ===
                { name: 'add_fillet', description: 'Add fillet (rounded edges) to specific edges of a body.', inputSchema: { type: 'object', properties: { body_name: { type: 'string', description: 'Target body.' }, radius: { type: 'number', default: 1, description: 'Fillet radius (mm).' }, edge_indices: { type: 'array', description: 'Edge indices (0-based). Omit for all edges.', items: { type: 'integer' } } }, required: ['body_name', 'radius'] } },
                { name: 'add_chamfer', description: 'Add chamfer (beveled edges) to specific edges of a body.', inputSchema: { type: 'object', properties: { body_name: { type: 'string', description: 'Target body.' }, distance: { type: 'number', default: 1, description: 'Chamfer distance (mm).' }, edge_indices: { type: 'array', description: 'Edge indices (0-based). Omit for all edges.', items: { type: 'integer' } } }, required: ['body_name', 'distance'] } },
                { name: 'combine_selection', description: 'Boolean operation on selected bodies. First selection is the target.', inputSchema: { type: 'object', properties: { operation: { type: 'string', enum: ['join', 'cut', 'intersect'], description: 'Boolean operation.' }, new_body_name: { type: 'string', description: 'Result body name (optional).' } }, required: ['operation'] } },
                { name: 'combine_selection_all', description: 'Boolean operation on all selected bodies.', inputSchema: { type: 'object', properties: { operation: { type: 'string', enum: ['join', 'cut', 'intersect'], default: 'join', description: 'Boolean operation.' }, new_body_name: { type: 'string', description: 'Result body name (optional).' } } } },
                { name: 'combine_by_name', description: 'Boolean operation on two bodies by name.', inputSchema: { type: 'object', properties: { target_body: { type: 'string', description: 'Target body name.' }, tool_body: { type: 'string', description: 'Tool body name.' }, operation: { type: 'string', enum: ['join', 'cut', 'intersect'], description: 'Boolean operation.' }, new_body_name: { type: 'string', description: 'Result body name (optional).' } }, required: ['target_body', 'tool_body', 'operation'] } },

                // === Transformation & Visibility Tools ===
                { name: 'hide_body', description: 'Hide a body by name.', inputSchema: { type: 'object', properties: { body_name: { type: 'string', description: 'Body to hide.' } }, required: ['body_name'] } },
                { name: 'show_body', description: 'Show a hidden body by name.', inputSchema: { type: 'object', properties: { body_name: { type: 'string', description: 'Body to show.' } }, required: ['body_name'] } },
                { name: 'move_by_name', description: 'Move a body by X/Y/Z offsets.', inputSchema: { type: 'object', properties: { body_name: { type: 'string', description: 'Body to move.' }, x_dist: { type: 'number', default: 0, description: 'X distance (mm).' }, y_dist: { type: 'number', default: 0, description: 'Y distance (mm).' }, z_dist: { type: 'number', default: 0, description: 'Z distance (mm).' } }, required: ['body_name'] } },
                { name: 'rotate_by_name', description: 'Rotate a body around an axis.', inputSchema: { type: 'object', properties: { body_name: { type: 'string', description: 'Body to rotate.' }, axis: { type: 'string', enum: ['x', 'y', 'z'], default: 'z', description: 'Rotation axis.' }, angle: { type: 'number', default: 90, description: 'Angle (degrees).' }, cx: { type: 'number', default: 0, description: 'Rotation center X (mm).' }, cy: { type: 'number', default: 0, description: 'Rotation center Y (mm).' }, cz: { type: 'number', default: 0, description: 'Rotation center Z (mm).' } }, required: ['body_name'] } },

                // === Selection Tools ===
                { name: 'select_body', description: 'Select a single body by name.', inputSchema: { type: 'object', properties: { body_name: { type: 'string', description: 'Body to select.' } }, required: ['body_name'] } },
                { name: 'select_bodies', description: 'Select two bodies by name.', inputSchema: { type: 'object', properties: { body_name1: { type: 'string', description: 'First body.' }, body_name2: { type: 'string', description: 'Second body.' } }, required: ['body_name1', 'body_name2'] } },
                { name: 'select_all_bodies', description: 'Select all bodies in the document.', inputSchema: { type: 'object', properties: {} } },

                // === Sketch System (LOT 2) ===
                { name: 'sketch_create', description: 'Create a new sketch on a plane or body face.', inputSchema: { type: 'object', properties: { plane: { type: 'string', enum: ['xy', 'xz', 'yz'], default: 'xy', description: 'Base plane.' }, name: { type: 'string', description: 'Sketch name.' }, offset: { type: 'number', default: 0, description: 'Offset from base plane (mm).' }, face_body_name: { type: 'string', description: 'Create sketch on a face of this body instead.' }, face_index: { type: 'integer', default: -1, description: 'Face index when using face_body_name. -1 means use plane instead.' } } } },
                { name: 'sketch_add_line', description: 'Add a line to a sketch.', inputSchema: { type: 'object', properties: { sketch_name: { type: 'string', description: 'Target sketch.' }, x1: { type: 'number', default: 0 }, y1: { type: 'number', default: 0 }, x2: { type: 'number', default: 50 }, y2: { type: 'number', default: 0 } }, required: ['sketch_name'] } },
                { name: 'sketch_add_circle', description: 'Add a circle to a sketch.', inputSchema: { type: 'object', properties: { sketch_name: { type: 'string', description: 'Target sketch.' }, cx: { type: 'number', default: 0, description: 'Center X (mm).' }, cy: { type: 'number', default: 0, description: 'Center Y (mm).' }, radius: { type: 'number', default: 25, description: 'Radius (mm).' } }, required: ['sketch_name', 'radius'] } },
                { name: 'sketch_add_arc', description: 'Add an arc through 3 points.', inputSchema: { type: 'object', properties: { sketch_name: { type: 'string', description: 'Target sketch.' }, x1: { type: 'number', default: 0 }, y1: { type: 'number', default: 0 }, x2: { type: 'number', default: 25 }, y2: { type: 'number', default: 25 }, x3: { type: 'number', default: 50 }, y3: { type: 'number', default: 0 } }, required: ['sketch_name'] } },
                { name: 'sketch_add_rectangle', description: 'Add a rectangle to a sketch.', inputSchema: { type: 'object', properties: { sketch_name: { type: 'string', description: 'Target sketch.' }, x1: { type: 'number', default: -25, description: 'Corner 1 X (mm).' }, y1: { type: 'number', default: -15, description: 'Corner 1 Y (mm).' }, x2: { type: 'number', default: 25, description: 'Corner 2 X (mm).' }, y2: { type: 'number', default: 15, description: 'Corner 2 Y (mm).' } }, required: ['sketch_name'] } },
                { name: 'sketch_add_polygon', description: 'Add a regular polygon to a sketch.', inputSchema: { type: 'object', properties: { sketch_name: { type: 'string', description: 'Target sketch.' }, cx: { type: 'number', default: 0 }, cy: { type: 'number', default: 0 }, radius: { type: 'number', default: 25, description: 'Circumscribed radius (mm).' }, num_sides: { type: 'integer', default: 6, description: 'Number of sides.' } }, required: ['sketch_name'] } },
                { name: 'sketch_add_spline', description: 'Add a fitted spline through points.', inputSchema: { type: 'object', properties: { sketch_name: { type: 'string', description: 'Target sketch.' }, points: { type: 'array', items: { type: 'array', items: { type: 'number' } }, description: 'Array of [x, y] points (mm). e.g. [[0,0],[25,30],[50,0]]' } }, required: ['sketch_name', 'points'] } },
                { name: 'sketch_add_text', description: 'Add text to a sketch for embossing/debossing.', inputSchema: { type: 'object', properties: { sketch_name: { type: 'string', description: 'Target sketch.' }, text: { type: 'string', default: 'Hello', description: 'Text content.' }, x: { type: 'number', default: 0 }, y: { type: 'number', default: 0 }, height: { type: 'number', default: 10, description: 'Text height (mm).' }, font_name: { type: 'string', default: 'Arial', description: 'Font name.' } }, required: ['sketch_name', 'text'] } },
                { name: 'sketch_extrude', description: 'Extrude a sketch profile to create material (new/join) or REMOVE material (cut). Use operation="cut" to make notches, slots, pockets, holes, grooves, engravings, or any subtractive operation. Use operation="join" to add material to an existing body. Use operation="new" (default) to create a separate body. Supports symmetric extrusion (both sides at once). WORKFLOW: 1) sketch_create on a plane, 2) sketch_add_rectangle/circle/etc, 3) sketch_extrude with the right operation.', inputSchema: { type: 'object', properties: { sketch_name: { type: 'string', description: 'Source sketch.' }, profile_index: { type: 'integer', default: 0, description: 'Profile index.' }, height: { type: 'number', default: 10, description: 'Extrusion height (mm). For symmetric, this is the TOTAL height (half on each side).' }, direction: { type: 'string', enum: ['positive', 'negative'], default: 'positive', description: 'Direction (ignored if symmetric).' }, symmetric: { type: 'boolean', default: false, description: 'Extrude equally on both sides of the sketch plane.' }, operation: { type: 'string', enum: ['new', 'join', 'cut', 'intersect'], default: 'new', description: 'Feature operation. Use "cut" to remove material (notches, slots, pockets).' }, body_name: { type: 'string', description: 'New body name (for operation="new" only).' } }, required: ['sketch_name', 'height'] } },

                // === Advanced Modeling (LOT 2) ===
                { name: 'create_revolve', description: 'Revolve a sketch profile around an axis (vases, wheels, axles).', inputSchema: { type: 'object', properties: { sketch_name: { type: 'string', description: 'Source sketch.' }, profile_index: { type: 'integer', default: 0 }, axis: { type: 'string', enum: ['x', 'y', 'z'], default: 'x', description: 'Revolution axis.' }, angle: { type: 'number', default: 360, description: 'Revolution angle (degrees).' }, body_name: { type: 'string', description: 'New body name.' } }, required: ['sketch_name'] } },
                { name: 'create_loft', description: 'Create a smooth transition between profiles from 2+ sketches.', inputSchema: { type: 'object', properties: { sketch_names: { type: 'array', items: { type: 'string' }, description: 'Sketch names (at least 2).' }, body_name: { type: 'string', description: 'New body name.' }, is_closed: { type: 'boolean', default: false, description: 'Close the loft.' } }, required: ['sketch_names'] } },
                { name: 'create_sweep', description: 'Sweep a profile along a path from another sketch.', inputSchema: { type: 'object', properties: { profile_sketch_name: { type: 'string', description: 'Sketch with the profile.' }, path_sketch_name: { type: 'string', description: 'Sketch with the sweep path.' }, profile_index: { type: 'integer', default: 0 }, body_name: { type: 'string', description: 'New body name.' } }, required: ['profile_sketch_name', 'path_sketch_name'] } },
                { name: 'create_construction_plane', description: 'Create a construction plane offset from a base plane.', inputSchema: { type: 'object', properties: { plane: { type: 'string', enum: ['xy', 'xz', 'yz'], default: 'xy', description: 'Base plane.' }, offset: { type: 'number', default: 10, description: 'Offset distance (mm).' }, name: { type: 'string', description: 'Plane name.' } } } },

                // === Query & Measurement Tools ===
                { name: 'get_bounding_box', description: 'Get bounding box info (min/max coordinates, size, center) of a body.', inputSchema: { type: 'object', properties: { body_name: { type: 'string', description: 'Body name.' } }, required: ['body_name'] } },
                { name: 'get_body_center', description: 'Get geometric center and center of mass of a body.', inputSchema: { type: 'object', properties: { body_name: { type: 'string', description: 'Body name.' } }, required: ['body_name'] } },
                { name: 'get_body_dimensions', description: 'Get detailed dimensions (length, width, height, volume, surface area) of a body.', inputSchema: { type: 'object', properties: { body_name: { type: 'string', description: 'Body name.' } }, required: ['body_name'] } },
                { name: 'get_faces_info', description: 'Get face info (type, area, normal, center) for a body. Indices are 0-based.', inputSchema: { type: 'object', properties: { body_name: { type: 'string', description: 'Body name.' } }, required: ['body_name'] } },
                { name: 'get_edges_info', description: 'Get edge info (type, length, direction) for a body. Indices are 0-based.', inputSchema: { type: 'object', properties: { body_name: { type: 'string', description: 'Body name.' } }, required: ['body_name'] } },
                { name: 'get_mass_properties', description: 'Get mass properties (volume, mass, center of mass, inertia) of a body.', inputSchema: { type: 'object', properties: { body_name: { type: 'string', description: 'Body name.' }, material_density: { type: 'number', default: 1.0, description: 'Material density (g/cm³).' } }, required: ['body_name'] } },
                { name: 'get_body_relationships', description: 'Get spatial relationship (distance, interference, relative position) between two bodies.', inputSchema: { type: 'object', properties: { body_name: { type: 'string', description: 'First body.' }, other_body_name: { type: 'string', description: 'Second body.' } }, required: ['body_name', 'other_body_name'] } },
                { name: 'measure_distance', description: 'Measure distance between two bodies (center-to-center and bounding box clearance).', inputSchema: { type: 'object', properties: { body_name1: { type: 'string', description: 'First body.' }, body_name2: { type: 'string', description: 'Second body.' } }, required: ['body_name1', 'body_name2'] } },
                { name: 'list_bodies', description: 'List all bodies with names, visibility, volume, center, and size.', inputSchema: { type: 'object', properties: {} } },

                // === Export (LOT 3) ===
                { name: 'export_stl', description: 'Export as STL for 3D printing.', inputSchema: { type: 'object', properties: { file_path: { type: 'string', description: 'Output file path.' }, body_name: { type: 'string', description: 'Export only this body (optional).' }, refinement: { type: 'string', enum: ['low', 'medium', 'high'], default: 'medium', description: 'Mesh refinement.' } }, required: ['file_path'] } },
                { name: 'export_step', description: 'Export as STEP for CAD interoperability.', inputSchema: { type: 'object', properties: { file_path: { type: 'string', description: 'Output file path.' } }, required: ['file_path'] } },
                { name: 'export_f3d', description: 'Export as Fusion 360 archive (.f3d).', inputSchema: { type: 'object', properties: { file_path: { type: 'string', description: 'Output file path.' } }, required: ['file_path'] } },

                // === Materials & Appearance (LOT 3) ===
                { name: 'set_material', description: 'Assign a physical material (steel, aluminum, ABS, etc.) to a body.', inputSchema: { type: 'object', properties: { body_name: { type: 'string', description: 'Target body.' }, material_name: { type: 'string', default: 'Steel', description: 'Material name (partial match).' }, library_name: { type: 'string', default: 'Fusion 360 Material Library', description: 'Library name.' } }, required: ['body_name', 'material_name'] } },
                { name: 'set_appearance', description: 'Assign a visual appearance to a body.', inputSchema: { type: 'object', properties: { body_name: { type: 'string', description: 'Target body.' }, appearance_name: { type: 'string', default: 'Steel - Satin', description: 'Appearance name (partial match).' }, library_name: { type: 'string', default: 'Fusion 360 Appearance Library', description: 'Library name.' } }, required: ['body_name', 'appearance_name'] } },

                // === Parametric Design (LOT 3) ===
                { name: 'set_user_parameter', description: 'Create or update a named parameter for parametric design.', inputSchema: { type: 'object', properties: { name: { type: 'string', description: 'Parameter name.' }, value: { type: 'number', default: 0, description: 'Value.' }, units: { type: 'string', default: 'mm', description: 'Units.' }, expression: { type: 'string', description: 'Expression (overrides value). e.g. "width * 2"' } }, required: ['name'] } },
                { name: 'get_user_parameter', description: 'Get user parameter(s). Returns all if no name specified.', inputSchema: { type: 'object', properties: { name: { type: 'string', description: 'Parameter name (optional).' } } } },

                // === Utility (LOT 3) ===
                { name: 'capture_viewport', description: 'Capture viewport screenshot as PNG.', inputSchema: { type: 'object', properties: { file_path: { type: 'string', description: 'Output image path.' }, width: { type: 'integer', default: 1920, description: 'Width (pixels).' }, height: { type: 'integer', default: 1080, description: 'Height (pixels).' } }, required: ['file_path'] } },
                { name: 'delete_all_features', description: 'Delete all features from the timeline, resetting the design.', inputSchema: { type: 'object', properties: {} } },
                { name: 'debug_coordinate_info', description: 'Output coordinate system and unit debug info.', inputSchema: { type: 'object', properties: { show_details: { type: 'boolean', default: true, description: 'Show detailed info.' } } } },
                { name: 'debug_body_placement', description: 'Output detailed placement info for a body (center, bounding box, edges).', inputSchema: { type: 'object', properties: { body_name: { type: 'string', description: 'Body name.' } }, required: ['body_name'] } },

                // === Existing Design Interaction ===
                { name: 'rename_body', description: 'Rename an existing body.', inputSchema: { type: 'object', properties: { body_name: { type: 'string', description: 'Current body name.' }, new_name: { type: 'string', description: 'New body name.' } }, required: ['body_name', 'new_name'] } },
                { name: 'get_design_info', description: 'Get overall design info — document name, units, body/component/feature counts, body names.', inputSchema: { type: 'object', properties: {} } },
                { name: 'list_features', description: 'List all features in the timeline with type, name, and suppression status.', inputSchema: { type: 'object', properties: {} } },
                { name: 'list_sketches', description: 'List all sketches with name, visibility, profile count, and curve count.', inputSchema: { type: 'object', properties: {} } },
                { name: 'list_components', description: 'List all components and occurrences in the design with their bodies.', inputSchema: { type: 'object', properties: {} } },
                { name: 'suppress_feature', description: 'Suppress a feature in the timeline (non-destructive disable).', inputSchema: { type: 'object', properties: { feature_index: { type: 'integer', description: 'Feature index in timeline (0-based). Use list_features to find indices.' } }, required: ['feature_index'] } },
                { name: 'unsuppress_feature', description: 'Unsuppress a previously suppressed feature.', inputSchema: { type: 'object', properties: { feature_index: { type: 'integer', description: 'Feature index in timeline (0-based).' } }, required: ['feature_index'] } },
                { name: 'delete_feature', description: 'Delete a specific feature from the timeline.', inputSchema: { type: 'object', properties: { feature_index: { type: 'integer', description: 'Feature index in timeline (0-based).' } }, required: ['feature_index'] } },

                // === Intuitive High-Level Tools ===
                // These tools let Claude naturally pick the right approach from plain language.
                {
                    name: 'create_tube',
                    description: 'Create a hollow tube/pipe/cylinder. Use when the user says "tube", "hollow cylinder", "pipe with walls", or needs a cylindrical shell. Much simpler than creating two cylinders + boolean cut.',
                    inputSchema: { type: 'object', properties: {
                        outer_radius: { type: 'number', default: 25, description: 'Outer radius (mm).' },
                        inner_radius: { type: 'number', default: 20, description: 'Inner radius (mm). Must be less than outer_radius.' },
                        height: { type: 'number', default: 50, description: 'Height (mm).' },
                        body_name: { type: 'string', description: 'Body name (optional).' },
                        plane: { type: 'string', enum: ['xy', 'xz', 'yz'], default: 'xy', description: 'Base plane.' },
                        cx: { type: 'number', default: 0 }, cy: { type: 'number', default: 0 }, cz: { type: 'number', default: 0 },
                        z_placement: { type: 'string', enum: ['center', 'bottom', 'top'], default: 'center' },
                        x_placement: { type: 'string', enum: ['center', 'left', 'right'], default: 'center' },
                        y_placement: { type: 'string', enum: ['center', 'front', 'back'], default: 'center' },
                        direction: { type: 'string', enum: ['positive', 'negative'], default: 'positive' }
                    }, required: ['outer_radius', 'inner_radius'] }
                },
                {
                    name: 'create_counterbore_hole',
                    description: 'Create a counterbore hole (stepped hole for socket head cap screws). Use when the user says "counterbore", "stepped hole", "bolt hole with recess", or "hex socket screw hole".',
                    inputSchema: { type: 'object', properties: {
                        body_name: { type: 'string', description: 'Target body.' },
                        face_index: { type: 'integer', default: 0, description: 'Face index (0-based).' },
                        x: { type: 'number', default: 0, description: 'Hole center X (mm).' },
                        y: { type: 'number', default: 0, description: 'Hole center Y (mm).' },
                        hole_diameter: { type: 'number', default: 5, description: 'Through-hole diameter (mm).' },
                        hole_depth: { type: 'number', default: 0, description: 'Hole depth (mm). 0 = through all.' },
                        counterbore_diameter: { type: 'number', default: 10, description: 'Counterbore diameter (mm).' },
                        counterbore_depth: { type: 'number', default: 3, description: 'Counterbore depth (mm).' }
                    }, required: ['body_name', 'hole_diameter', 'counterbore_diameter'] }
                },
                {
                    name: 'create_countersink_hole',
                    description: 'Create a countersink hole (tapered entry for flat head screws). Use when the user says "countersink", "flat head screw hole", "flush screw hole", or "tapered hole entry".',
                    inputSchema: { type: 'object', properties: {
                        body_name: { type: 'string', description: 'Target body.' },
                        face_index: { type: 'integer', default: 0, description: 'Face index (0-based).' },
                        x: { type: 'number', default: 0, description: 'Hole center X (mm).' },
                        y: { type: 'number', default: 0, description: 'Hole center Y (mm).' },
                        hole_diameter: { type: 'number', default: 5, description: 'Through-hole diameter (mm).' },
                        hole_depth: { type: 'number', default: 0, description: 'Hole depth (mm). 0 = through all.' },
                        countersink_diameter: { type: 'number', default: 10, description: 'Countersink top diameter (mm).' },
                        countersink_angle: { type: 'number', default: 90, description: 'Countersink angle (degrees). 82° for US flat head, 90° for metric.' }
                    }, required: ['body_name', 'hole_diameter', 'countersink_diameter'] }
                },
                {
                    name: 'sketch_mirror',
                    description: 'Mirror all sketch geometry across an axis. Use when the user wants symmetric sketch profiles, or says "mirror the sketch".',
                    inputSchema: { type: 'object', properties: {
                        sketch_name: { type: 'string', description: 'Target sketch.' },
                        mirror_axis: { type: 'string', enum: ['x', 'y'], default: 'x', description: 'Mirror axis.' }
                    }, required: ['sketch_name'] }
                },
                {
                    name: 'sketch_offset',
                    description: 'Offset sketch curves to create parallel geometry (walls, channels, outlines). Use when the user says "offset", "parallel curve", "wall thickness in sketch".',
                    inputSchema: { type: 'object', properties: {
                        sketch_name: { type: 'string', description: 'Target sketch.' },
                        offset_distance: { type: 'number', default: 5, description: 'Offset distance (mm).' },
                        curve_index: { type: 'integer', default: 0, description: 'Curve to offset (0-based).' },
                        direction_point_x: { type: 'number', default: 0, description: 'Direction point X (mm).' },
                        direction_point_y: { type: 'number', default: 0, description: 'Direction point Y (mm).' }
                    }, required: ['sketch_name', 'offset_distance'] }
                },
                {
                    name: 'sketch_fillet',
                    description: 'Add a fillet (rounded corner) between two sketch curves. Use when the user wants to round sketch corners before extruding.',
                    inputSchema: { type: 'object', properties: {
                        sketch_name: { type: 'string', description: 'Target sketch.' },
                        curve_index_1: { type: 'integer', default: 0, description: 'First curve index.' },
                        curve_index_2: { type: 'integer', default: 1, description: 'Second curve index.' },
                        radius: { type: 'number', default: 5, description: 'Fillet radius (mm).' }
                    }, required: ['sketch_name', 'radius'] }
                },
                {
                    name: 'create_component',
                    description: 'Create a new component from existing bodies. Use when the user wants to organize parts into sub-assemblies, or says "make this a component", "group these bodies".',
                    inputSchema: { type: 'object', properties: {
                        body_names: { type: 'array', items: { type: 'string' }, description: 'Bodies to move into the component.' },
                        component_name: { type: 'string', description: 'Component name.' }
                    } }
                },
                {
                    name: 'extrude_to_object',
                    description: 'Extrude a sketch profile until it reaches another body surface. Use when the user says "extrude up to", "extrude until it touches", "extend to surface of".',
                    inputSchema: { type: 'object', properties: {
                        sketch_name: { type: 'string', description: 'Source sketch.' },
                        target_body_name: { type: 'string', description: 'Body whose surface defines the extrusion limit.' },
                        profile_index: { type: 'integer', default: 0 },
                        operation: { type: 'string', enum: ['new', 'join', 'cut', 'intersect'], default: 'new' },
                        body_name: { type: 'string', description: 'New body name.' }
                    }, required: ['sketch_name', 'target_body_name'] }
                },

                // === Advanced Sketch Tools ===
                {
                    name: 'sketch_add_constraint',
                    description: 'Add a geometric constraint between sketch curves. Use when the user says "make parallel", "make perpendicular", "align", "fix position", "make tangent", "make equal", "make symmetric". Constraints keep geometry relationships consistent during parametric editing.',
                    inputSchema: { type: 'object', properties: {
                        sketch_name: { type: 'string', description: 'Target sketch name.' },
                        constraint_type: { type: 'string', enum: ['coincident', 'parallel', 'perpendicular', 'tangent', 'equal', 'fix', 'horizontal', 'vertical', 'concentric', 'collinear', 'smooth', 'midpoint', 'symmetry'], description: 'Constraint type.' },
                        entity_one: { type: 'integer', description: 'First curve index (0-based). Use get_edges_info or list_sketches to find indices.' },
                        entity_two: { type: 'integer', description: 'Second curve index (0-based). Not needed for fix/horizontal/vertical.' },
                        symmetry_line: { type: 'integer', description: 'Curve index of the symmetry axis. Only for symmetry constraint.' }
                    }, required: ['sketch_name', 'constraint_type', 'entity_one'] }
                },
                {
                    name: 'sketch_add_dimension',
                    description: 'Add a parametric dimension to sketch geometry. Use when the user specifies exact sizes like "make this line 50mm", "set the angle to 45°", "diameter should be 20mm". Dimensions drive parametric design — changing a dimension updates all dependent geometry.',
                    inputSchema: { type: 'object', properties: {
                        sketch_name: { type: 'string', description: 'Target sketch name.' },
                        dimension_type: { type: 'string', enum: ['distance', 'angular', 'radial', 'diameter', 'horizontal', 'vertical'], description: 'Dimension type. distance=between two curves, angular=angle between two lines, radial/diameter=for circles/arcs.' },
                        value: { type: 'number', description: 'Dimension value in mm (distance/radial/diameter) or degrees (angular).' },
                        entity_one: { type: 'integer', description: 'First curve index (0-based).' },
                        entity_two: { type: 'integer', description: 'Second curve index (0-based). Not needed for radial/diameter.' }
                    }, required: ['sketch_name', 'dimension_type', 'value', 'entity_one'] }
                },

                // === Undo & Escape Hatch ===
                {
                    name: 'undo',
                    description: 'Undo the last operation. Same as Ctrl+Z. Use when the user says "undo", "go back", "revert that", "that was wrong", or when you made a mistake and need to fix it.',
                    inputSchema: { type: 'object', properties: {} }
                },
                {
                    name: 'execute_code',
                    description: 'Execute arbitrary Python code inside Fusion 360. LAST RESORT — try sketch_extrude(operation="cut") for notches/slots, combine_by_name for booleans, shell_body for hollowing FIRST. Only use this if no specific tool covers the operation. Has access to: adsk, app, ui, design, root, math, json. The last expression value is returned.',
                    inputSchema: { type: 'object', properties: {
                        code: { type: 'string', description: 'Python code to execute. Has pre-loaded: adsk, app, ui, design, root, math, json.' }
                    }, required: ['code'] }
                }
            ];
            logDebug(`Returning ${tools.length} tools`);
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
            parameters: parameters,
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
        const server = new Fusion360MCPServer();
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
