// server.js - Compatible avec la version japonaise de fusion_mcp_server.py
const fs = require('fs');
const path = require('path');

const commandFilePath = path.join(require('os').homedir(), 'Documents', 'fusion_command.txt');
const logFilePath = path.join(__dirname, 'mcp_server.log');

const log = (message) => {
    const logEntry = `[${new Date().toISOString()}] ${message}\n`;
    fs.appendFileSync(logFilePath, logEntry);
    console.error(logEntry.trim());
};

log("🚀 Serveur MCP Fusion démarré - Compatible version HYBRIDE");

process.stdin.setEncoding('utf8');

process.stdin.on('data', (chunk) => {
    try {
        const data = chunk.trim();
        if (!data || data.length === 0) {
            return;
        }
        
        log(`📨 Données reçues: ${data}`);
        
        if (!data.startsWith('{')) {
            log(`⚠️ Données non-JSON ignorées: ${data}`);
            return;
        }
        
        const request = JSON.parse(data);
        
        if (request.method === "initialize") {
            const response = {
                jsonrpc: "2.0",
                id: request.id,
                result: {
                    protocolVersion: "2024-11-05",
                    capabilities: { tools: {} },
                    serverInfo: {
                        name: "fusion-mcp-server-hybrid",
                        version: "3.0.0"
                    }
                }
            };
            process.stdout.write(JSON.stringify(response) + '\n');
            log("✅ Serveur japonais initialisé");
            
        } else if (request.method === "tools/list") {
            const response = {
                jsonrpc: "2.0",
                id: request.id,
                result: {
                    tools: [
                        // === CRÉATION DE FORMES ===
                        {
                            name: "create_cube",
                            description: "Crée un cube dans Fusion 360",
                            inputSchema: {
                                type: "object",
                                properties: {
                                    size: { type: "number", description: "Taille du cube en mm" },
                                    name: { type: "string", description: "Nom du cube (optionnel)" },
                                    plane: { type: "string", description: "Plan de construction: xy, yz, xz (optionnel)" },
                                    cx: { type: "number", description: "Position X du centre en mm (optionnel)" },
                                    cy: { type: "number", description: "Position Y du centre en mm (optionnel)" },
                                    cz: { type: "number", description: "Position Z du centre en mm (optionnel)" }
                                },
                                required: ["size"]
                            }
                        },
                        {
                            name: "create_cylinder",
                            description: "Crée un cylindre dans Fusion 360",
                            inputSchema: {
                                type: "object",
                                properties: {
                                    radius: { type: "number", description: "Rayon en mm" },
                                    height: { type: "number", description: "Hauteur en mm" },
                                    name: { type: "string", description: "Nom du cylindre (optionnel)" },
                                    plane: { type: "string", description: "Plan de construction: xy, yz, xz (optionnel)" },
                                    cx: { type: "number", description: "Position X du centre en mm (optionnel)" },
                                    cy: { type: "number", description: "Position Y du centre en mm (optionnel)" },
                                    cz: { type: "number", description: "Position Z du centre en mm (optionnel)" }
                                },
                                required: ["radius", "height"]
                            }
                        },
                        {
                            name: "create_box",
                            description: "Crée une boîte rectangulaire dans Fusion 360",
                            inputSchema: {
                                type: "object",
                                properties: {
                                    width: { type: "number", description: "Largeur en mm" },
                                    depth: { type: "number", description: "Profondeur en mm" },
                                    height: { type: "number", description: "Hauteur en mm" },
                                    name: { type: "string", description: "Nom de la boîte (optionnel)" },
                                    plane: { type: "string", description: "Plan de construction: xy, yz, xz (optionnel)" },
                                    cx: { type: "number", description: "Position X du centre en mm (optionnel)" },
                                    cy: { type: "number", description: "Position Y du centre en mm (optionnel)" },
                                    cz: { type: "number", description: "Position Z du centre en mm (optionnel)" }
                                },
                                required: ["width", "depth", "height"]
                            }
                        },
                        {
                            name: "create_sphere",
                            description: "Crée une sphère dans Fusion 360",
                            inputSchema: {
                                type: "object",
                                properties: {
                                    radius: { type: "number", description: "Rayon en mm" },
                                    name: { type: "string", description: "Nom de la sphère (optionnel)" },
                                    plane: { type: "string", description: "Plan de construction: xy, yz, xz (optionnel)" },
                                    cx: { type: "number", description: "Position X du centre en mm (optionnel)" },
                                    cy: { type: "number", description: "Position Y du centre en mm (optionnel)" },
                                    cz: { type: "number", description: "Position Z du centre en mm (optionnel)" }
                                },
                                required: ["radius"]
                            }
                        },
                        {
                            name: "create_cone",
                            description: "Crée un cône dans Fusion 360",
                            inputSchema: {
                                type: "object",
                                properties: {
                                    radius: { type: "number", description: "Rayon de base en mm" },
                                    height: { type: "number", description: "Hauteur en mm" },
                                    name: { type: "string", description: "Nom du cône (optionnel)" },
                                    plane: { type: "string", description: "Plan de construction: xy, yz, xz (optionnel)" },
                                    cx: { type: "number", description: "Position X du centre en mm (optionnel)" },
                                    cy: { type: "number", description: "Position Y du centre en mm (optionnel)" },
                                    cz: { type: "number", description: "Position Z du centre en mm (optionnel)" }
                                },
                                required: ["radius", "height"]
                            }
                        },
                        {
                            name: "create_sq_pyramid",
                            description: "Crée une pyramide carrée dans Fusion 360",
                            inputSchema: {
                                type: "object",
                                properties: {
                                    side: { type: "number", description: "Côté de la base en mm" },
                                    height: { type: "number", description: "Hauteur en mm" },
                                    name: { type: "string", description: "Nom de la pyramide (optionnel)" },
                                    plane: { type: "string", description: "Plan de construction: xy, yz, xz (optionnel)" },
                                    cx: { type: "number", description: "Position X du centre en mm (optionnel)" },
                                    cy: { type: "number", description: "Position Y du centre en mm (optionnel)" },
                                    cz: { type: "number", description: "Position Z du centre en mm (optionnel)" }
                                },
                                required: ["side", "height"]
                            }
                        },
                        {
                            name: "create_tri_pyramid",
                            description: "Crée une pyramide triangulaire dans Fusion 360",
                            inputSchema: {
                                type: "object",
                                properties: {
                                    side: { type: "number", description: "Côté de la base en mm" },
                                    height: { type: "number", description: "Hauteur en mm" },
                                    name: { type: "string", description: "Nom de la pyramide (optionnel)" },
                                    plane: { type: "string", description: "Plan de construction: xy, yz, xz (optionnel)" },
                                    cx: { type: "number", description: "Position X du centre en mm (optionnel)" },
                                    cy: { type: "number", description: "Position Y du centre en mm (optionnel)" },
                                    cz: { type: "number", description: "Position Z du centre en mm (optionnel)" }
                                },
                                required: ["side", "height"]
                            }
                        },
                        
                        // === MANIPULATION D'OBJETS ===
                        {
                            name: "move_selection",
                            description: "Déplace les objets sélectionnés",
                            inputSchema: {
                                type: "object",
                                properties: {
                                    x: { type: "number", description: "Distance X en mm" },
                                    y: { type: "number", description: "Distance Y en mm" },
                                    z: { type: "number", description: "Distance Z en mm" }
                                },
                                required: ["x", "y", "z"]
                            }
                        },
                        {
                            name: "rotate_selection",
                            description: "Fait tourner l'objet sélectionné",
                            inputSchema: {
                                type: "object",
                                properties: {
                                    axis: { type: "string", description: "Axe de rotation: x, y, z" },
                                    angle: { type: "number", description: "Angle en degrés" },
                                    cx: { type: "number", description: "Centre X en mm" },
                                    cy: { type: "number", description: "Centre Y en mm" },
                                    cz: { type: "number", description: "Centre Z en mm" }
                                },
                                required: ["axis", "angle", "cx", "cy", "cz"]
                            }
                        },
                        {
                            name: "combine_selection",
                            description: "Combine deux objets sélectionnés",
                            inputSchema: {
                                type: "object",
                                properties: {
                                    operation: { type: "string", description: "Opération: join, cut, intersect" }
                                },
                                required: ["operation"]
                            }
                        },
                        {
                            name: "combine_by_name",
                            description: "Combine deux objets par leur nom",
                            inputSchema: {
                                type: "object",
                                properties: {
                                    target: { type: "string", description: "Nom de l'objet cible" },
                                    tool: { type: "string", description: "Nom de l'objet outil" },
                                    operation: { type: "string", description: "Opération: join, cut, intersect" }
                                },
                                required: ["target", "tool", "operation"]
                            }
                        },
                        
                        // === SÉLECTION ===
                        {
                            name: "select_body",
                            description: "Sélectionne un objet par son nom",
                            inputSchema: {
                                type: "object",
                                properties: {
                                    name: { type: "string", description: "Nom de l'objet à sélectionner" }
                                },
                                required: ["name"]
                            }
                        },
                        {
                            name: "select_bodies",
                            description: "Sélectionne deux objets par leur nom",
                            inputSchema: {
                                type: "object",
                                properties: {
                                    name1: { type: "string", description: "Nom du premier objet" },
                                    name2: { type: "string", description: "Nom du second objet" }
                                },
                                required: ["name1", "name2"]
                            }
                        },
                        {
                            name: "select_edges",
                            description: "Sélectionne les arêtes d'un objet",
                            inputSchema: {
                                type: "object",
                                properties: {
                                    bodyName: { type: "string", description: "Nom de l'objet" },
                                    edgeType: { type: "string", description: "Type d'arêtes: all ou circular" }
                                },
                                required: ["bodyName", "edgeType"]
                            }
                        },
                        {
                            name: "add_fillet",
                            description: "Ajoute un congé aux arêtes sélectionnées",
                            inputSchema: {
                                type: "object",
                                properties: {
                                    radius: { type: "number", description: "Rayon du congé en mm" }
                                },
                                required: ["radius"]
                            }
                        },
                        
                        // === UTILITAIRES ===
                        {
                            name: "undo",
                            description: "Annule la dernière opération",
                            inputSchema: {
                                type: "object",
                                properties: {},
                                required: []
                            }
                        },
                        {
                            name: "redo",
                            description: "Refait la dernière opération annulée",
                            inputSchema: {
                                type: "object",
                                properties: {},
                                required: []
                            }
                        }
                    ]
                }
            };
            process.stdout.write(JSON.stringify(response) + '\n');
            log("📋 Liste des outils japonais envoyée");
            
        } else if (request.method === "tools/call") {
            const toolName = request.params.name;
            const args = request.params.arguments || {};
            
            let command = "";
            
            // === CRÉATION DE FORMES ===
            if (toolName === "create_cube") {
                const size = args.size || 50;
                const name = args.name || "";
                const plane = args.plane || "xy";
                const cx = args.cx || 0;
                const cy = args.cy || 0;
                const cz = args.cz || 0;
                command = `create_cube ${size} ${name} ${plane} ${cx} ${cy} ${cz}`.trim();
                
            } else if (toolName === "create_cylinder") {
                const radius = args.radius || 25;
                const height = args.height || 50;
                const name = args.name || "";
                const plane = args.plane || "xy";
                const cx = args.cx || 0;
                const cy = args.cy || 0;
                const cz = args.cz || 0;
                command = `create_cylinder ${radius} ${height} ${name} ${plane} ${cx} ${cy} ${cz}`.trim();
                
            } else if (toolName === "create_box") {
                const width = args.width || 50;
                const depth = args.depth || 50;
                const height = args.height || 50;
                const name = args.name || "";
                const plane = args.plane || "xy";
                const cx = args.cx || 0;
                const cy = args.cy || 0;
                const cz = args.cz || 0;
                command = `create_box ${width} ${depth} ${height} ${name} ${plane} ${cx} ${cy} ${cz}`.trim();
                
            } else if (toolName === "create_sphere") {
                const radius = args.radius || 25;
                const name = args.name || "";
                const plane = args.plane || "xy";
                const cx = args.cx || 0;
                const cy = args.cy || 0;
                const cz = args.cz || 0;
                command = `create_sphere ${radius} ${name} ${plane} ${cx} ${cy} ${cz}`.trim();
                
            } else if (toolName === "create_cone") {
                const radius = args.radius || 25;
                const height = args.height || 50;
                const name = args.name || "";
                const plane = args.plane || "xy";
                const cx = args.cx || 0;
                const cy = args.cy || 0;
                const cz = args.cz || 0;
                command = `create_cone ${radius} ${height} ${name} ${plane} ${cx} ${cy} ${cz}`.trim();
                
            } else if (toolName === "create_sq_pyramid") {
                const side = args.side || 50;
                const height = args.height || 50;
                const name = args.name || "";
                const plane = args.plane || "xy";
                const cx = args.cx || 0;
                const cy = args.cy || 0;
                const cz = args.cz || 0;
                command = `create_sq_pyramid ${side} ${height} ${name} ${plane} ${cx} ${cy} ${cz}`.trim();
                
            } else if (toolName === "create_tri_pyramid") {
                const side = args.side || 50;
                const height = args.height || 50;
                const name = args.name || "";
                const plane = args.plane || "xy";
                const cx = args.cx || 0;
                const cy = args.cy || 0;
                const cz = args.cz || 0;
                command = `create_tri_pyramid ${side} ${height} ${name} ${plane} ${cx} ${cy} ${cz}`.trim();
                
            // === MANIPULATION ===
            } else if (toolName === "move_selection") {
                const x = args.x || 0;
                const y = args.y || 0;
                const z = args.z || 0;
                command = `move_selection ${x} ${y} ${z}`;
                
            } else if (toolName === "rotate_selection") {
                const axis = args.axis || "z";
                const angle = args.angle || 90;
                const cx = args.cx || 0;
                const cy = args.cy || 0;
                const cz = args.cz || 0;
                command = `rotate_selection ${axis} ${angle} ${cx} ${cy} ${cz}`;
                
            } else if (toolName === "combine_selection") {
                const operation = args.operation || "join";
                command = `combine_selection ${operation}`;
                
            } else if (toolName === "combine_by_name") {
                const target = args.target || "";
                const tool = args.tool || "";
                const operation = args.operation || "join";
                command = `combine_by_name ${target} ${tool} ${operation}`;
                
            // === SÉLECTION ===
            } else if (toolName === "select_body") {
                const name = args.name || "";
                command = `select_body ${name}`;
                
            } else if (toolName === "select_bodies") {
                const name1 = args.name1 || "";
                const name2 = args.name2 || "";
                command = `select_bodies ${name1} ${name2}`;
                
            } else if (toolName === "select_edges") {
                const bodyName = args.bodyName || "";
                const edgeType = args.edgeType || "all";
                command = `select_edges ${bodyName} ${edgeType}`;
                
            } else if (toolName === "add_fillet") {
                const radius = args.radius || 5;
                command = `add_fillet ${radius}`;
                
            // === UTILITAIRES ===
            } else if (toolName === "undo") {
                command = "undo";
                
            } else if (toolName === "redo") {
                command = "redo";
            }
            
            if (command) {
                log(`🔧 Commande: ${command}`);
                fs.writeFileSync(commandFilePath, command, 'utf8');
                log(`✅ Écrit dans: ${commandFilePath}`);
                
                const response = {
                    jsonrpc: "2.0",
                    id: request.id,
                    result: {
                        content: [
                            {
                                type: "text",
                                text: `✅ Commande '${command}' envoyée à Fusion 360`
                            }
                        ]
                    }
                };
                process.stdout.write(JSON.stringify(response) + '\n');
                log("✔️ Réponse envoyée");
            } else {
                log(`❌ Commande inconnue: ${toolName}`);
            }
        }
        
    } catch (error) {
        log(`❌ ERREUR: ${error.message}`);
        if (request && request.id) {
            const errorResponse = {
                jsonrpc: "2.0",
                id: request.id,
                error: { code: -1, message: error.message }
            };
            process.stdout.write(JSON.stringify(errorResponse) + '\n');
        }
    }
});

log("👂 En attente de Claude Desktop ...");