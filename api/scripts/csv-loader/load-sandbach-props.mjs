#!/usr/bin/env node
/**
 * Parse Sandbach CSV file and generate properties array for AI service mock data
 * Run: node scripts/csv-loader/load-sandbach-props.mjs
 */

import fs from 'fs';
import { fileURLToPath } from 'url';
import path from 'path';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

// Resolve to workspace root (parent of api/scripts/csv-loader)
const WORKSPACE_ROOT = path.resolve(__dirname, '../../..');
const CSV_PATH = path.join(WORKSPACE_ROOT, 'search_results(4).csv');

console.log('📄 Loading Sandbach property data...');
console.log(`   CSV path: ${CSV_PATH}`);

try {
    const csvContent = fs.readFileSync(CSV_PATH, 'utf-8');
    const lines = csvContent.trim().split('\n');
    
    console.log(`✅ Found ${lines.length - 1} properties (minus header)`);
    
    const properties = [];
    
    for (let i = 1; i < lines.length; i++) {
        const line = lines[i];
        if (!line.trim()) continue;
        
        // Parse CSV row (handle quoted fields with commas)
        const cols = [];
        let current = '';
        let inQuotes = false;
        
        for (let j = 0; j < line.length; j++) {
            const char = line[j];
            if (char === '"') {
                inQuotes = !inQuotes;
            } else if (char === ',' && !inQuotes) {
                cols.push(current.trim());
                current = '';
            } else {
                current += char;
            }
        }
        cols.push(current.trim());
        
        // Map CSV columns: Address, URL, Last sold, Price paid, Floor area, £/sqm, Type, Beds, Tenure, Plot size
        if (cols.length >= 9) {
            // Price can be like "387000" or "387k" - handle both
            let priceStr = cols[3].trim();
            const hasK = /k/i.test(priceStr);
            if (hasK) {
                priceStr = priceStr.replace('k', '').trim();
            } else {
                // Remove commas and currency symbols but don't multiply by 1000
                priceStr = priceStr.replace(/£|,|,/g, '');
            }
            
            properties.push({
                id: properties.length + 1,
                address_line1: cols[0].replace(/["']/g, '').replace(/,\s*/, ' '),
                town: "Sandbach",
                postcode: "CW1",
                outcode: "CW1",
                property_type: (cols[6] || 'unknown').toLowerCase().trim()
                    .replace(/[-\s]/g, '_'),
                num_beds: parseInt(cols[7]) || 0,
                price_paid: parseInt(priceStr) || 0,
                date_sold: cols[2]?.trim() || '',
                latitude: null,
                longitude: null,
            });
        }
    }
    
    console.log(`✅ Parsed ${properties.length} properties`);
    console.log('\n📊 Property type distribution:');
    const types = properties.reduce((acc, p) => {
        acc[p.property_type] = (acc[p.property_type] || 0) + 1;
        return acc;
    }, {});
    Object.entries(types).forEach(([type, count]) => {
        console.log(`   - ${type}: ${count}`);
    });
    
    // Calculate price range for reference
    const prices = properties.map(p => p.price_paid);
    console.log('\n💰 Price stats:', 
        `Min: £${Math.min(...prices).toLocaleString()}`,
        `Max: £${Math.max(...prices).toLocaleString()} `,
        `Avg: £${(prices.reduce((a,b)=>a+b,0)/prices.length).toLocaleString()}`);
    
    // Save to file for AI service using absolute path
    const outputPath = 'C:/Users/aps33/Projects/Kimi-Abode/ai-service/data/sandbach_properties.json';
    fs.writeFileSync(outputPath, JSON.stringify(properties, null, 2));
    console.log(`\n✅ Saved to: ${outputPath}`);
    console.log(`   File size: ${(fs.statSync(outputPath).size / 1024).toFixed(1)} KB`);
    
    // Output first 3 for preview
    console.log('\n--- Sample properties ---');
    console.log(JSON.stringify(properties.slice(0, 3), null, 2));
    
} catch (err) {
    console.error('❌ Error:', err.message);
    process.exit(1);
}