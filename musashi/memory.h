/*
 * Memory API for Musashi 4.x
 */

typedef enum {
    MEM_READ = 'R',
    MEM_WRITE = 'W',
    INVALID_READ = 'r',
    INVALID_WRITE = 'w',
    MEM_MAP = 'M',
} mem_operation_t;

typedef enum {
    MEM_SIZE_8 = 8,
    MEM_SIZE_16 = 16,
    MEM_SIZE_32 = 32
} mem_width_t;

typedef enum {
	MEM_MAP_ROM,
	MEM_MAP_RAM,
	MEM_MAP_DEVICE,
} mem_map_flavor_t;

typedef uint32_t (*mem_device_handler_t)(mem_operation_t operation, 
                                         uint32_t address, 
                                         uint32_t size,
                                         uint32_t value);

typedef void (*mem_trace_handler_t)(mem_operation_t operation,
                                    uint32_t address,
                                    uint32_t size,
                                    uint32_t value);

bool mem_add_memory(uint32_t base, uint32_t size, bool writable);
bool mem_add_device(uint32_t base, uint32_t size);

void mem_set_device_handler(mem_device_handler_t handler);
void mem_set_trace_handler(mem_trace_handler_t handler);
void mem_enable_tracing(bool enable);
void mem_enable_bus_error(bool enable); 

uint32_t mem_read_memory(uint32_t address, uint32_t size);
void mem_write_memory(uint32_t address, mem_width_t width, uint32_t value);
void mem_write_bulk(uint32_t address, uint8_t *buffer, uint32_t size);
